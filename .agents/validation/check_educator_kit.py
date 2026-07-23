#!/usr/bin/env python3
"""Validate the repository-only EDU-01A educator-kit contract.

The checker uses only repository source files and the Python standard library.
It validates closed canonical JSON, exact not-run pilot facts, canonical versus
educator-review evidence, and the complete source/config/evaluator closure for
the 12 learning-path targets. Controlled inputs are read through bounded,
no-follow descriptor chains with stable file and parent identities. It never
opens learner outputs, imports repository runtime code, or contacts an external
service.

Approved-document rebind flow (deliberate and never automatic):

1. Review the complete byte diff of all three bound Markdown documents and
   confirm that the not-run/no-human-evidence/no-G4 boundary remains true.
2. Run ``python .agents/validation/check_educator_kit.py --print-document-hashes``;
   this command refuses to print hashes when a forbidden affirmative claim is
   present.
3. Update ``DOCUMENT_SHA256`` in the same reviewed change; never update a hash
   merely to make this checker pass.
4. Run this checker and ``pytest -q tests/test_educator_kit.py`` again.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import stat
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
KIT_PATH = Path("docs/educator_kit.json")
SCHEMA_PATH = Path("docs/educator_kit.schema.json")
GUIDE_PATH = Path("docs/educator_guide.md")
PILOT_PATH = Path("docs/educator_pilot_protocol.md")
DOC_MAP_PATH = Path("docs/README.md")
MENU_PATH = Path("src/mclab/learner_menu.py")
CATALOG_PATH = Path("src/mclab/application/catalog.py")
BATCH_PATH = Path("src/mclab/batch.py")
CONFIG_PATH = Path("src/mclab/config.py")
COMPLETION_PATH = Path("src/mclab/completion.py")

KIT_SHA256 = "0f066ea1059298c0e19d44f59a63aba22781ab56ee61fd331e794ba29a7f1b8d"
SCHEMA_SHA256 = "bfa909ed58f36a9831384bc9e57423b0a2c34168496d126881ddd01a81d563c2"
COMPLETION_SOURCE_SHA256 = "8781ea476f63d62b92199423dbbe2d0e57e0157ba08ffbde7423335dae5957ca"
CATALOG_SOURCE_SHA256 = "69cfe5c22f63be5009090b8c0cd351fcb0f4c8c617631c83f5bb23582e38a320"
CONFIG_SOURCE_SHA256 = "abe0ed19f2b80224dcd0d8ffda11d417901e0881ce700e40459e28f1b86905e3"
DOCUMENT_SHA256 = {
    GUIDE_PATH: "6d367ce77d5acd2f44176a694c4eea51a6aea31329dc9e5c42cbfcf1d73c4b33",
    PILOT_PATH: "68fc1c79a77906d2c14dd0502550eaf0942ff63c04f73bed27bc0d66e0040651",
    DOC_MAP_PATH: "1b7442c708502368c3bec0e4fded2baa61c1628a0b4428ef434bcda5decb9c9a",
}
CONFIG_SHA256 = {
    "configs/lab01_msd/default.yaml": "76fb695e8b871998e5dcfbfead91817ca76d29ac200ea6696aee304d3fc5ef32",
    "configs/lab01_msd/interactive_pull.yaml": "16c82e7429bb0c870b3196d2e3c627986b154844f74a79ced06865a3b387b7a3",
    "configs/lab02_pid/default.yaml": "f6ac40bdf355b0fe59b6303b422c179ccf204bef2936c243c416258d7f02edf7",
    "configs/lab02_pid/interactive_disturbance.yaml": "e1eb53960e0f47bc06f3869d7db68aed23c87996cfbcca266437fb2b36d4ff1e",
    "configs/lab03_2dof/joint_space_2dof.yaml": "430c49469a4792de6375c92433cd647f177bf0131732f2d8eac9f292af6e423c",
    "configs/lab03_2dof/task_space_2dof.yaml": "28f11e39f12bd080af6cdbffeaa791f08b0b937043678c202fbc99e5db3d1f4b",
    "configs/lab03_2dof/condition_aware_dls_2dof.yaml": "edb979b4bac83af55a726227e599d9252e7ec02d6442095dab02684766da0cc3",
    "configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml": "86a13cf555d414dc5255b9391485ac5271dd7e98a15f44f2432fa998ede753f0",
    "configs/lab04_panda/neutral_hold.yaml": "8eed510091c75cc061f0c3ceb8d7de53bb61df75d12344524c43480495ae3fdd",
    "configs/lab04_panda/cartesian_reach.yaml": "cd263bd609bb09c85c1750a24a8111f1bfede4aa2f024d2f942e116814d2f37c",
    "configs/lab04_panda/interactive_virtual_wall.yaml": "d260eb98136c48157003d02d83a5248078393c550d7488f33740f8a8c52a00df",
}
MAX_INPUT_BYTES = 2_000_000
READ_CHUNK_BYTES = 64 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_JSON_STRING_CHARS = 250_000
MAX_JSON_TOTAL_STRING_CHARS = 1_000_000
MAX_CANONICAL_JSON_BYTES = MAX_INPUT_BYTES
WINDOWS_REPARSE_ATTRIBUTE = 0x400
OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
STAT_SUPPORTS_DIR_FD = os.stat in os.supports_dir_fd
STAT_SUPPORTS_NOFOLLOW = os.stat in os.supports_follow_symlinks

TOP_LEVEL_KEYS = frozenset(
    {
        "canonical_sources",
        "kit_id",
        "learning_outcomes",
        "learning_path",
        "pilot",
        "rubric",
        "schema_version",
        "scope",
        "unresolved_decisions",
    }
)
PATH_STEP_KEYS = frozenset(
    {
        "action_kind",
        "canonical_completion_evidence",
        "command",
        "description",
        "educator_review_evidence",
        "group",
        "label",
        "mode",
        "order",
        "outcome_ids",
        "planned_minutes",
        "target_id",
        "title",
    }
)
CANONICAL_EVIDENCE_KEYS = frozenset(
    {
        "minimum_plot_count",
        "record_kind",
        "required_artifacts",
        "required_presets",
        "requires_learner_control",
        "requires_note",
        "requires_observation",
        "requires_plot",
        "requires_prediction",
        "requires_run",
        "status",
    }
)
OUTCOME_KEYS = frozenset({"assessment_evidence", "id", "statement", "steps", "summative_steps"})
RUBRIC_DIMENSION_KEYS = frozenset({"id", "levels", "name", "outcome_ids"})
HANDS_ON_TARGET_IDS = frozenset(
    {
        "lab01.interactive-pull",
        "lab02.interactive-disturbance",
        "lab03.condition-aware-dls-2dof",
        "lab04.interactive-virtual-wall",
    }
)
EXPECTED_TARGET_IDS = (
    "lab01.default",
    "lab01.interactive-pull",
    "lab02.default",
    "lab02.interactive-disturbance",
    "lab03.joint-space-2dof",
    "lab03.task-space-2dof",
    "lab03.condition-aware-dls-2dof",
    "lab03.condition-aware-dls-adaptive-speed-retarget-2dof",
    "lab04.neutral-hold",
    "lab04.cartesian-reach",
    "lab04.interactive-virtual-wall",
    "batch.all",
)
EXPECTED_OUTCOME_STEPS = {
    "LO-01": (1, 2),
    "LO-02": (3, 4),
    "LO-03": (5, 6, 7, 8),
    "LO-04": (9, 10, 11),
    "LO-05": tuple(range(1, 13)),
}
EXPECTED_SUMMATIVE_STEPS = {
    "LO-01": (2,),
    "LO-02": (4,),
    "LO-03": (7, 8),
    "LO-04": (10, 11),
    "LO-05": (12,),
}
EXPECTED_CONCRETE_BATCH_TARGET_IDS = (
    "batch.lab01_msd_compare",
    "batch.lab02_pid_compare",
    "batch.lab03_2dof_compare",
    "batch.lab04_wall_compare",
    "batch.lab04_cartesian_compare",
)
EXPECTED_SCOPE = {
    "actual_accessibility_validation": "not-run",
    "external_contact_authorized": False,
    "g4_satisfied": False,
    "human_evidence": False,
    "participant_recruitment_authorized": False,
    "pilot_execution": "not-run",
    "repository_only": True,
    "timing_basis": "planned-not-measured",
}
EXPECTED_CANONICAL_SOURCES = {
    "catalog_target_ids": "src/mclab/application/catalog.py:LEARNING_PATH_TARGET_IDS",
    "completion_evaluator": "src/mclab/completion.py:evaluate_completion",
    "completion_rules": "src/mclab/application/catalog.py:ScenarioCatalog.default",
    "educator_guide": "docs/educator_guide.md",
    "learning_path": "src/mclab/learner_menu.py:LEARNING_PATH",
    "pilot_protocol": "docs/educator_pilot_protocol.md",
}
EXPECTED_UNRESOLVED = (
    {
        "id": "consent-and-institutional-review",
        "status": "owner-or-institution-decision",
    },
    {
        "id": "participant-and-educator-coordinator",
        "status": "owner-decision",
    },
    {
        "id": "pilot-data-retention-and-access",
        "status": "owner-or-institution-decision",
    },
    {
        "id": "supported-real-device-and-assistive-technology-matrix",
        "status": "owner-decision",
    },
)
EXPECTED_GATES = {
    "novice-sample": "exactly 6 novices in the fixed primary cohort supply a recorded result for every required measure; withdrawals or missing measures fail the gate and are not replaced or pooled",
    "educator-adoption": "at least 1 independent educator passes every frozen Lab01 adoption checklist item using only the guides",
    "first-report-time": "the fixed 6-person primary cohort median time to first valid Lab01 default report is at most 10 minutes",
    "learning-comprehension": "at least 5 of the fixed 6-person primary novice cohort pass all four frozen predict-manipulate-observe-replay comprehension items",
    "novice-core-flow": "at least 5 of the fixed 6-person primary novice cohort pass every frozen core-flow item with at most one non-directive hint and no directive hint",
    "severity": "zero unresolved severity-1 or severity-2 findings",
    "sus": "the mean standard System Usability Scale score across all 6 primary novices is at least 68 with no missing item or participant total",
}
EXPECTED_RESULT_KEYS = frozenset(
    {
        "educator_adoption_success_count",
        "first_report_median_minutes",
        "learning_comprehension_count",
        "novice_core_flow_success_count",
        "sev1_count",
        "sev2_count",
        "sus_mean",
    }
)
AUTOMATIC_REVIEW_EVIDENCE = (
    "priority-plot-interpretation",
    "report",
    "worksheet",
)
HANDS_ON_REVIEW_EVIDENCE = (
    "post-completion-outcome-review",
    "report",
    "worksheet",
)
COMPARISON_REVIEW_EVIDENCE = (
    "answered-prediction-check-prompts-external",
    "cross-lab-claim",
    "priority-plot-selection",
)
HEADLESS_FALLBACK_COMMANDS = (
    "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml --headless --plot --plots essential --open-report",
    "python -m mclab run lab02 --config configs/lab02_pid/interactive_disturbance.yaml --headless --plot --plots essential --open-report",
    "python -m mclab run lab03 --config configs/lab03_2dof/condition_aware_dls_2dof.yaml --headless --plot --plots dls_disturbance --open-report",
    "python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml --headless --plot --plots wall --open-report",
)

GUIDE_HEADINGS = (
    "Teaching model",
    "Learning outcomes",
    "Before class",
    "Four-session lesson plan",
    "Exact learning-path commands",
    "Completion and submission checks",
    "Learning-outcome rubric",
    "Accessibility and privacy boundary",
)
PILOT_HEADINGS = (
    "Status and authorization boundary",
    "Purpose",
    "Required sample and roles",
    "Frozen test materials",
    "Novice procedure",
    "Educator procedure",
    "Severity taxonomy",
    "G4-aligned pilot thresholds",
    "Evidence record",
    "Analysis and decision",
)
GUIDE_MARKERS = (
    "210 planned minutes",
    "These values have not been measured with learners",
    "There is no `mclab verify` command.",
    "does **not** prove viewer usability",
    "Use `not_assessed` when required evidence was not collected",
    "Close wall → Back away → Re-enter wall",
    "canonical completion and educator review separate",
    "answered Prediction Check or defended claim",
    "Record those hands-on and viewer outcomes as `not_assessed`",
    "formative submission rubric, not a canonical completion rule, G4 metric",
    "do not recruit, contact, or collect data from participants",
)
PILOT_MARKERS = (
    "**Status: not run. Authorization: not authorized.**",
    "Do not recruit or contact participants",
    "fixed primary cohort of exactly **6 novices**",
    "At least **1 educator**",
    "lab01.default",
    "lab01.interactive-pull",
    "Start a monotonic timer",
    "valid Lab01 default report",
    "pass all four frozen comprehension items",
    "passes every frozen Lab01 adoption checklist item",
    "**Sev1:**",
    "**Sev2:**",
    "conventional median",
    "arithmetic mean is at least 68",
    "do not replace the participant",
    "Do not pool",
    "They do not by themselves satisfy G4",
    "Never commit participant notes",
)
LOCAL_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\s]+)(?:\s+[^)]*)?\)")
CLAIM_NEGATION_RE = re.compile(
    r"\b(?:cannot|can't|do not|does not|did not|has not|have not|had not|"
    r"is not|are not|was not|were not|must not|never|no|not|without|"
    r"unauthorized|unapproved|unrun)\b",
    re.IGNORECASE,
)
CLAIM_CONDITIONAL_PREFIX_RE = re.compile(
    r"^(?:if|when|before|after|once|until|unless|only if|only when|only after)\b",
    re.IGNORECASE,
)
FORBIDDEN_CLAIM_PATTERNS = (
    (
        "pilot-authorization",
        re.compile(
            r"\b(?:classroom\s+trial|pilot|study|trial)\b.{0,120}(?:"
            r"\b(?:is|was|were)\s+(?:now\s+)?(?:fully\s+)?"
            r"(?:approved|authorized|cleared)\b|"
            r"\b(?:has|have)\s+(?:now\s+)?been\s+(?:fully\s+)?"
            r"(?:approved|authorized|cleared)\b|"
            r"\b(?:now\s+)?has\s+(?:received\s+)?"
            r"(?:approval|authorization|clearance)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "pilot-completion",
        re.compile(
            r"\b(?:classroom\s+trial|pilot|study|trial)\b.{0,160}(?:"
            r"\b(?:completed|concluded|finished)\s+successfully\b|"
            r"\b(?:has|have|had)\s+(?:now\s+)?been\s+"
            r"(?:completed|finished|run)\b|"
            r"\bresults?\s+(?:are|is|were)\s+(?:now\s+)?final\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "human-evidence",
        re.compile(
            r"(?:\b(?:educator|human|novice|participant)\w*\s+"
            r"(?:evidence|observation|result)\w*|"
            r"\b(?:evidence|observation|result)\w*\s+(?:from|of)\s+"
            r"(?:educator|human|novice|participant)\w*)\s+(?:now\s+)?"
            r"(?:confirms?|demonstrates?|establishes?|proves?|"
            r"substantiates?|validates?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "g4-satisfaction",
        re.compile(
            r"\b(?:g4|human-facing|production[-\s]+readiness|production)\b"
            r".{0,100}\b(?:gate|readiness|requirement)\w*\b.{0,80}"
            r"\b(?:are|has\s+(?:now\s+)?been|have\s+(?:now\s+)?been|is|were)\s+"
            r"(?:fully\s+)?(?:complete|met|passed|satisfied)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "headless-hands-on-credit",
        re.compile(
            r"\b(?:automatic|headless)\s+(?:fallback|run)\b.{0,80}"
            r"\b(?:counts?\s+as|earns?|grants?|satisfies)\b.{0,80}"
            r"\b(?:hands-on|interactive)\b.{0,40}\b(?:completion|credit)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "educator-review-canonical",
        re.compile(
            r"\b(?:educator(?:'s)?\s+)?outcome\s+review\b.{0,80}(?:"
            r"\b(?:is|becomes?)\s+(?:now\s+)?part\s+of\b|"
            r"\b(?:changes?|counts?\s+toward|determines?|satisfies)\b)"
            r".{0,80}\b(?:canonical|machine)\b.{0,40}"
            r"\b(?:completion|decision|input|verdict)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt-as-answer",
        re.compile(
            r"\b(?:displaying|showing|the\s+(?:availability|presence)\s+of)\b"
            r".{0,80}\b(?:prediction\s+check|prompt)\w*\b.{0,80}"
            r"\b(?:automatically\s+)?(?:constitutes?|counts?\s+as|demonstrates?|"
            r"proves?|records?|saves?)\b.{0,80}\b(?:answer|response)\w*\b",
            re.IGNORECASE,
        ),
    ),
    (
        "step-12-shortcut",
        re.compile(
            r"\b(?:course\s+comparison|final\s+path\s+step|step\s+12)\b"
            r".{0,100}\b(?:closes?|completes?|passes?)\b.{0,100}"
            r"(?:\balone\b|\bas\s+soon\s+as\b|\bby\s+itself\b|"
            r"\bonly\s+(?:because|requirement)\b|\bsufficient\b)"
            r".{0,80}\b(?:course\s+)?report\b|"
            r"\b(?:course\s+comparison|final\s+path\s+step|step\s+12)\b"
            r".{0,100}\b(?:closes?|completes?|passes?)\b.{0,100}"
            r"\b(?:course\s+)?report\s+exists?\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class ValidationMetric:
    name: str
    value: int | str


class DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


class ContractInputError(ValueError):
    """Raised when a controlled repository input cannot be read safely."""


@dataclass
class _OpenedDirectory:
    path: Path
    descriptor: int
    identity: tuple[int, int, int, int, int]
    label: str
    parent: _OpenedDirectory | None = None
    name: str | None = None


@dataclass
class _DirectoryChain:
    entries: list[_OpenedDirectory]

    @property
    def leaf(self) -> _OpenedDirectory:
        return self.entries[-1]

    def assert_current(self) -> None:
        for entry in self.entries:
            _assert_directory_current(entry)


@dataclass(frozen=True)
class _StatView:
    st_ctime_ns: int
    st_dev: int
    st_file_attributes: int
    st_ino: int
    st_mode: int
    st_mtime_ns: int
    st_reparse_tag: int
    st_size: int


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value}")


def _parse_finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite JSON number {value}")
    return result


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _json_structure_error(document: Any, relative: Path) -> str | None:
    nodes = 0
    total_string_chars = 0
    stack: list[tuple[Any, int]] = [(document, 0)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            return f"JSON_LIMIT: {relative}: node count exceeds {MAX_JSON_NODES}"
        if depth > MAX_JSON_DEPTH:
            return f"JSON_LIMIT: {relative}: nesting depth exceeds {MAX_JSON_DEPTH}"
        if isinstance(value, dict):
            if nodes + len(stack) + (2 * len(value)) > MAX_JSON_NODES:
                return f"JSON_LIMIT: {relative}: node count exceeds {MAX_JSON_NODES}"
            for key, child in value.items():
                nodes += 1
                if nodes > MAX_JSON_NODES:
                    return f"JSON_LIMIT: {relative}: node count exceeds {MAX_JSON_NODES}"
                if len(key) > MAX_JSON_STRING_CHARS:
                    return f"JSON_LIMIT: {relative}: string length exceeds {MAX_JSON_STRING_CHARS}"
                total_string_chars += len(key)
                if total_string_chars > MAX_JSON_TOTAL_STRING_CHARS:
                    return (
                        f"JSON_LIMIT: {relative}: total string characters exceed "
                        f"{MAX_JSON_TOTAL_STRING_CHARS}"
                    )
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            if nodes + len(stack) + len(value) > MAX_JSON_NODES:
                return f"JSON_LIMIT: {relative}: node count exceeds {MAX_JSON_NODES}"
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            if len(value) > MAX_JSON_STRING_CHARS:
                return f"JSON_LIMIT: {relative}: string length exceeds {MAX_JSON_STRING_CHARS}"
            total_string_chars += len(value)
            if total_string_chars > MAX_JSON_TOTAL_STRING_CHARS:
                return (
                    f"JSON_LIMIT: {relative}: total string characters exceed "
                    f"{MAX_JSON_TOTAL_STRING_CHARS}"
                )
    return None


def _canonical_json_bytes(document: Any, relative: Path) -> tuple[bytes | None, str | None]:
    encoder = json.JSONEncoder(
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    canonical = bytearray()
    try:
        for chunk in encoder.iterencode(document):
            encoded = chunk.encode("utf-8", errors="strict")
            if len(canonical) + len(encoded) + 1 > MAX_CANONICAL_JSON_BYTES:
                return (
                    None,
                    f"JSON_LIMIT: {relative}: canonical bytes exceed {MAX_CANONICAL_JSON_BYTES}",
                )
            canonical.extend(encoded)
    except (RecursionError, UnicodeEncodeError, ValueError) as exc:
        return None, f"INVALID_JSON: {relative}: canonical serialization failed: {exc}"
    canonical.extend(b"\n")
    return bytes(canonical), None


def _windows_path_attributes(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_attributes = kernel32.GetFileAttributesW
    get_attributes.argtypes = (wintypes.LPCWSTR,)
    get_attributes.restype = wintypes.DWORD
    attributes = int(get_attributes(str(path)))
    if attributes == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    return attributes


def _windows_descriptor_metadata(descriptor: int) -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information.restype = wintypes.BOOL
    information = FileAttributeTagInfo()
    handle = msvcrt.get_osfhandle(descriptor)
    if not get_information(
        handle,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(information.file_attributes), int(information.reparse_tag)


def _stat_view(
    value: os.stat_result,
    *,
    file_attributes: int | None = None,
    reparse_tag: int | None = None,
) -> os.stat_result | _StatView:
    if file_attributes is None and reparse_tag is None:
        return value
    return _StatView(
        st_ctime_ns=int(value.st_ctime_ns),
        st_dev=int(value.st_dev),
        st_file_attributes=int(
            getattr(value, "st_file_attributes", 0) if file_attributes is None else file_attributes
        ),
        st_ino=int(value.st_ino),
        st_mode=int(value.st_mode),
        st_mtime_ns=int(value.st_mtime_ns),
        st_reparse_tag=int(
            getattr(value, "st_reparse_tag", 0) if reparse_tag is None else reparse_tag
        ),
        st_size=int(value.st_size),
    )


def _descriptor_stat(descriptor: int) -> os.stat_result | _StatView:
    value = os.fstat(descriptor)
    if os.name != "nt":
        return value
    attributes, reparse_tag = _windows_descriptor_metadata(descriptor)
    return _stat_view(value, file_attributes=attributes, reparse_tag=reparse_tag)


def _is_windows_reparse_point(value: Any) -> bool:
    return bool(int(getattr(value, "st_file_attributes", 0)) & WINDOWS_REPARSE_ATTRIBUTE)


def _stat_identity(value: Any) -> tuple[int, int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        stat.S_IFMT(value.st_mode),
        int(getattr(value, "st_file_attributes", 0)),
        int(getattr(value, "st_reparse_tag", 0)),
    )


def _file_snapshot(value: Any) -> tuple[int, int, int]:
    return (
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _validate_stat_kind(
    value: Any,
    *,
    label: str,
    context: str,
    directory: bool,
) -> None:
    if stat.S_ISLNK(value.st_mode):
        raise ContractInputError(f"SYMLINK_{context}: {label}")
    if _is_windows_reparse_point(value):
        raise ContractInputError(f"REPARSE_{context}: {label}")
    if directory and not stat.S_ISDIR(value.st_mode):
        raise ContractInputError(f"NON_DIRECTORY_{context}: {label}")
    if not directory and not stat.S_ISREG(value.st_mode):
        raise ContractInputError(f"NON_REGULAR_{context}: {label}")


def _open_windows_nofollow(path: Path, *, directory: bool) -> int:
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    desired_access = 0x00000080 if directory else 0x80000000
    share_mode = 0x00000001 | 0x00000002 | 0x00000004
    flags = 0x00200000 | (0x02000000 if directory else 0)
    handle = create_file(str(path), desired_access, share_mode, None, 3, flags, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    descriptor_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    try:
        return msvcrt.open_osfhandle(int(handle), descriptor_flags)
    except OSError:
        close_handle(handle)
        raise


def _open_nofollow(
    path: Path,
    *,
    directory: bool,
    parent_descriptor: int | None = None,
    name: str | None = None,
) -> int:
    if os.name == "nt":
        return _open_windows_nofollow(path, directory=directory)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ContractInputError("NOFOLLOW_FILE_DESCRIPTOR_UNAVAILABLE")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    if directory:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if directory_flag is None:
            raise ContractInputError("DIRECTORY_FILE_DESCRIPTOR_UNAVAILABLE")
        flags |= directory_flag
    if parent_descriptor is None:
        return os.open(path, flags)
    if name is None:
        raise ContractInputError("MISSING_RELATIVE_OPEN_NAME")
    if not OPEN_SUPPORTS_DIR_FD:
        raise ContractInputError("RELATIVE_NOFOLLOW_OPEN_UNAVAILABLE")
    return os.open(name, flags, dir_fd=parent_descriptor)


def _entry_lstat(parent: _OpenedDirectory, name: str) -> os.stat_result | _StatView:
    if os.name != "nt":
        if not STAT_SUPPORTS_DIR_FD or not STAT_SUPPORTS_NOFOLLOW:
            raise ContractInputError("RELATIVE_NOFOLLOW_STAT_UNAVAILABLE")
        return os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
    path = parent.path / name
    value = os.lstat(path)
    return _stat_view(value, file_attributes=_windows_path_attributes(path))


def _path_lstat(path: Path) -> os.stat_result | _StatView:
    value = os.lstat(path)
    if os.name != "nt":
        return value
    return _stat_view(value, file_attributes=_windows_path_attributes(path))


def _open_directory(
    path: Path,
    *,
    label: str,
    parent: _OpenedDirectory | None = None,
    name: str | None = None,
) -> _OpenedDirectory:
    descriptor: int | None = None
    try:
        before = _path_lstat(path) if parent is None else _entry_lstat(parent, str(name))
        _validate_stat_kind(before, label=label, context="DIRECTORY", directory=True)
        identity = _stat_identity(before)
        descriptor = _open_nofollow(
            path,
            directory=True,
            parent_descriptor=parent.descriptor if parent is not None else None,
            name=name,
        )
        opened = _descriptor_stat(descriptor)
        after = _path_lstat(path) if parent is None else _entry_lstat(parent, str(name))
        for value in (opened, after):
            _validate_stat_kind(value, label=label, context="DIRECTORY", directory=True)
        if not (identity == _stat_identity(opened) == _stat_identity(after)):
            raise ContractInputError(f"CHANGED_DIRECTORY: {label}")
        return _OpenedDirectory(path, descriptor, identity, label, parent, name)
    except ContractInputError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except FileNotFoundError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ContractInputError(f"MISSING_FILE: {label}: {exc}") from exc
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ContractInputError(f"READ_DIRECTORY: {label}: {exc}") from exc


def _assert_directory_current(directory: _OpenedDirectory) -> None:
    try:
        descriptor_stat = _descriptor_stat(directory.descriptor)
        path_stat = (
            _path_lstat(directory.path)
            if directory.parent is None
            else _entry_lstat(directory.parent, str(directory.name))
        )
        for value in (descriptor_stat, path_stat):
            _validate_stat_kind(
                value,
                label=directory.label,
                context="DIRECTORY",
                directory=True,
            )
        if not (directory.identity == _stat_identity(descriptor_stat) == _stat_identity(path_stat)):
            raise ContractInputError(f"CHANGED_DIRECTORY: {directory.label}")
    except ContractInputError:
        raise
    except OSError as exc:
        raise ContractInputError(f"CHANGED_DIRECTORY: {directory.label}: {exc}") from exc


def _safe_relative_parts(relative: Path) -> tuple[str, ...]:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ContractInputError(f"UNSAFE_PATH: {relative}")
    parts = tuple(part for part in relative.parts if part != ".")
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise ContractInputError(f"UNSAFE_PATH: {relative}")
    return parts


@contextmanager
def _open_directory_chain(
    root: Path,
    relative_directory: Path | None = None,
) -> Iterator[_DirectoryChain]:
    root_path = Path(os.path.abspath(os.fspath(root)))
    if not root_path.is_absolute() or not root_path.anchor:
        raise ContractInputError("INVALID_REPOSITORY_ROOT")
    relative_parts: tuple[str, ...] = ()
    if relative_directory is not None and relative_directory.parts:
        relative_parts = _safe_relative_parts(relative_directory)
    entries: list[_OpenedDirectory] = []
    try:
        anchor = Path(root_path.anchor)
        current = _open_directory(anchor, label="<repository-root-ancestor>")
        entries.append(current)
        for part in root_path.parts[1:]:
            current = _open_directory(
                current.path / part,
                label="<repository-root-ancestor>",
                parent=current,
                name=part,
            )
            entries.append(current)
        for index, part in enumerate(relative_parts):
            label = Path(*relative_parts[: index + 1]).as_posix()
            current = _open_directory(
                current.path / part,
                label=label,
                parent=current,
                name=part,
            )
            entries.append(current)
        chain = _DirectoryChain(entries)
        chain.assert_current()
        yield chain
        chain.assert_current()
    finally:
        for entry in reversed(entries):
            try:
                os.close(entry.descriptor)
            except OSError:
                pass


def _read_regular_bytes(root: Path, relative: Path) -> bytes:
    parts = _safe_relative_parts(relative)
    normalized = Path(*parts)
    parent_relative = normalized.parent if len(parts) > 1 else None
    label = normalized.as_posix()
    descriptor: int | None = None
    try:
        with _open_directory_chain(root, parent_relative) as chain:
            parent = chain.leaf
            name = parts[-1]
            before = _entry_lstat(parent, name)
            _validate_stat_kind(before, label=label, context="INPUT", directory=False)
            if before.st_size > MAX_INPUT_BYTES:
                raise ContractInputError(f"INPUT_TOO_LARGE: {label}")
            descriptor = _open_nofollow(
                parent.path / name,
                directory=False,
                parent_descriptor=parent.descriptor,
                name=name,
            )
            opened = _descriptor_stat(descriptor)
            after_open = _entry_lstat(parent, name)
            for value in (opened, after_open):
                _validate_stat_kind(value, label=label, context="INPUT", directory=False)
            if not (_stat_identity(before) == _stat_identity(opened) == _stat_identity(after_open)):
                raise ContractInputError(f"CHANGED_INPUT: {label}")

            data = bytearray()
            while True:
                remaining = MAX_INPUT_BYTES + 1 - len(data)
                if remaining <= 0:
                    raise ContractInputError(f"INPUT_TOO_LARGE: {label}")
                chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_INPUT_BYTES:
                    raise ContractInputError(f"INPUT_TOO_LARGE: {label}")

            after_read = _descriptor_stat(descriptor)
            final_path = _entry_lstat(parent, name)
            chain.assert_current()
            for value in (after_read, final_path):
                _validate_stat_kind(value, label=label, context="INPUT", directory=False)
            if not (
                _stat_identity(before) == _stat_identity(after_read) == _stat_identity(final_path)
            ) or not (
                _file_snapshot(before)
                == _file_snapshot(opened)
                == _file_snapshot(after_open)
                == _file_snapshot(after_read)
                == _file_snapshot(final_path)
            ):
                raise ContractInputError(f"CHANGED_INPUT: {label}")
            if len(data) != after_read.st_size:
                raise ContractInputError(f"CHANGED_INPUT: {label}")
            return bytes(data)
    except ContractInputError:
        raise
    except FileNotFoundError as exc:
        raise ContractInputError(f"MISSING_FILE: {label}: {exc}") from exc
    except OSError as exc:
        raise ContractInputError(f"READ_ERROR: {label}: {exc}") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _safe_read_bytes(root: Path, relative: Path) -> tuple[bytes | None, str | None]:
    """Read one stable regular input through an anchored no-follow descriptor chain."""

    try:
        return _read_regular_bytes(root, relative), None
    except ContractInputError as exc:
        return None, str(exc)


def _decode_utf8(data: bytes, relative: Path) -> tuple[str | None, str | None]:
    try:
        return data.decode("utf-8", errors="strict"), None
    except UnicodeDecodeError as exc:
        return None, f"INVALID_UTF8: {relative}: {exc}"


def _safe_read(root: Path, relative: Path) -> tuple[str | None, str | None]:
    data, error = _safe_read_bytes(root, relative)
    if error or data is None:
        return None, error
    return _decode_utf8(data, relative)


def _load_json(
    root: Path,
    relative: Path,
) -> tuple[Any | None, str | None, bytes | None, str | None]:
    raw, error = _safe_read_bytes(root, relative)
    if error or raw is None:
        return None, None, None, error
    text, decode_error = _decode_utf8(raw, relative)
    if decode_error or text is None:
        return None, None, raw, decode_error
    try:
        document = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
        )
    except (json.JSONDecodeError, DuplicateKeyError, ValueError, RecursionError) as exc:
        return None, text, raw, f"INVALID_JSON: {relative}: {exc}"
    if b"\r" in raw:
        return document, text, raw, f"NON_LF_JSON: {relative} contains a carriage return"
    structure_error = _json_structure_error(document, relative)
    if structure_error:
        return None, text, raw, structure_error
    canonical, canonical_error = _canonical_json_bytes(document, relative)
    if canonical_error or canonical is None:
        return None, text, raw, canonical_error
    if raw != canonical:
        return document, text, raw, f"NON_CANONICAL_JSON: {relative}"
    return document, text, raw, None


def _typed_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _typed_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            _typed_equal(left, right) for left, right in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _exact_keys(value: Any, expected: frozenset[str], context: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"TYPE: {context} must be an object")
        return False
    actual = frozenset(value)
    if actual != expected:
        errors.append(f"KEYS: {context} expected {sorted(expected)!r}, got {sorted(actual)!r}")
        return False
    return True


def _string_list(value: Any, context: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"TYPE: {context} must be a non-empty string list")
        return ()
    result = tuple(value)
    if len(set(result)) != len(result):
        errors.append(f"DUPLICATE: {context} contains duplicate values")
    return result


def _expected_canonical_evidence(target_id: str, mode: str) -> dict[str, Any]:
    hands_on = mode == "hands-on"
    course = target_id == "batch.all"
    return {
        "minimum_plot_count": 0 if course else 1,
        "record_kind": "manifest_v1",
        "required_artifacts": (
            ["report", "worksheet", *EXPECTED_CONCRETE_BATCH_TARGET_IDS] if course else []
        ),
        "required_presets": (
            ["Close wall", "Back away", "Re-enter wall"]
            if target_id == "lab04.interactive-virtual-wall"
            else []
        ),
        "requires_learner_control": hands_on,
        "requires_note": hands_on,
        "requires_observation": hands_on,
        "requires_plot": not course,
        "requires_prediction": hands_on,
        "requires_run": True,
        "status": "completed",
    }


def _expected_review_evidence(mode: str) -> tuple[str, ...]:
    if mode == "comparison":
        return COMPARISON_REVIEW_EVIDENCE
    if mode == "hands-on":
        return HANDS_ON_REVIEW_EVIDENCE
    return AUTOMATIC_REVIEW_EVIDENCE


def _document_errors(document: Any) -> list[str]:
    errors: list[str] = []
    if not _exact_keys(document, TOP_LEVEL_KEYS, "educator kit", errors):
        return errors
    assert isinstance(document, dict)

    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        errors.append("VALUE: schema_version must be exact integer 1")
    if document["kit_id"] != "EDU-01A-repository-pilot-kit":
        errors.append("VALUE: unexpected kit_id")
    if not _typed_equal(document["canonical_sources"], EXPECTED_CANONICAL_SOURCES):
        errors.append("VALUE: canonical_sources drifted")
    if not _typed_equal(document["scope"], EXPECTED_SCOPE):
        errors.append("VALUE: repository-only/not-run scope drifted")
    if not _typed_equal(document["unresolved_decisions"], list(EXPECTED_UNRESOLVED)):
        errors.append("VALUE: unresolved owner/institution decisions drifted")

    outcomes = document["learning_outcomes"]
    if not isinstance(outcomes, list) or len(outcomes) != 5:
        errors.append("COUNT: learning_outcomes must contain exactly 5 rows")
        outcomes = []
    outcome_by_id: dict[str, dict[str, Any]] = {}
    for index, outcome in enumerate(outcomes, start=1):
        context = f"learning_outcomes[{index}]"
        if not _exact_keys(outcome, OUTCOME_KEYS, context, errors):
            continue
        assert isinstance(outcome, dict)
        outcome_id = outcome["id"]
        if not isinstance(outcome_id, str) or outcome_id not in EXPECTED_OUTCOME_STEPS:
            errors.append(f"VALUE: {context}.id is not LO-01..LO-05")
            continue
        if outcome_id in outcome_by_id:
            errors.append(f"DUPLICATE: learning outcome {outcome_id}")
        outcome_by_id[outcome_id] = outcome
        if not isinstance(outcome["statement"], str) or not outcome["statement"].strip():
            errors.append(f"TYPE: {context}.statement must be non-empty")
        _string_list(outcome["assessment_evidence"], f"{context}.assessment_evidence", errors)
        steps = outcome["steps"]
        if (
            not isinstance(steps, list)
            or any(type(step) is not int for step in steps)
            or tuple(steps) != EXPECTED_OUTCOME_STEPS[outcome_id]
        ):
            errors.append(f"VALUE: {context}.steps drifted")
        summative_steps = outcome["summative_steps"]
        if (
            not isinstance(summative_steps, list)
            or any(type(step) is not int for step in summative_steps)
            or tuple(summative_steps) != EXPECTED_SUMMATIVE_STEPS[outcome_id]
        ):
            errors.append(f"VALUE: {context}.summative_steps drifted")
    if tuple(outcome_by_id) != tuple(EXPECTED_OUTCOME_STEPS):
        errors.append("ORDER: learning outcomes must be LO-01 through LO-05")

    steps = document["learning_path"]
    if not isinstance(steps, list) or len(steps) != 12:
        errors.append("COUNT: learning_path must contain exactly 12 rows")
        steps = []
    for index, step in enumerate(steps, start=1):
        context = f"learning_path[{index}]"
        if not _exact_keys(step, PATH_STEP_KEYS, context, errors):
            continue
        assert isinstance(step, dict)
        if type(step["order"]) is not int or step["order"] != index:
            errors.append(f"VALUE: {context}.order must be exact integer {index}")
        if type(step["planned_minutes"]) is not int or not 1 <= step["planned_minutes"] <= 60:
            errors.append(f"VALUE: {context}.planned_minutes must be an integer from 1 to 60")
        raw_target_id = step["target_id"]
        target_id = raw_target_id if isinstance(raw_target_id, str) else ""
        if not target_id:
            errors.append(f"TYPE: {context}.target_id must be a non-empty string")
        if target_id != EXPECTED_TARGET_IDS[index - 1]:
            errors.append(f"VALUE: {context}.target_id drifted")
        expected_mode = (
            "comparison"
            if target_id == "batch.all"
            else "hands-on"
            if target_id in HANDS_ON_TARGET_IDS
            else "automatic"
        )
        if step["mode"] != expected_mode:
            errors.append(f"VALUE: {context}.mode must be {expected_mode}")
        expected_action = "batch" if target_id == "batch.all" else "run"
        if step["action_kind"] != expected_action:
            errors.append(f"VALUE: {context}.action_kind must be {expected_action}")
        canonical = step["canonical_completion_evidence"]
        if _exact_keys(
            canonical,
            CANONICAL_EVIDENCE_KEYS,
            f"{context}.canonical_completion_evidence",
            errors,
        ) and not _typed_equal(
            canonical,
            _expected_canonical_evidence(target_id, expected_mode),
        ):
            errors.append(f"VALUE: {context}.canonical_completion_evidence drifted")
        review_evidence = _string_list(
            step["educator_review_evidence"],
            f"{context}.educator_review_evidence",
            errors,
        )
        if review_evidence != _expected_review_evidence(expected_mode):
            errors.append(f"VALUE: {context}.educator_review_evidence drifted")
        outcome_ids = _string_list(step["outcome_ids"], f"{context}.outcome_ids", errors)
        if any(outcome_id not in EXPECTED_OUTCOME_STEPS for outcome_id in outcome_ids):
            errors.append(f"VALUE: {context}.outcome_ids contains an unknown outcome")
        for key in ("command", "description", "group", "label", "title"):
            if not isinstance(step[key], str) or not step[key].strip():
                errors.append(f"TYPE: {context}.{key} must be non-empty")
    if steps:
        minute_values = [step.get("planned_minutes") for step in steps if isinstance(step, dict)]
        if len(minute_values) != 12 or any(type(value) is not int for value in minute_values):
            errors.append("VALUE: all 12 planned-minute values must be exact integers")
        elif sum(minute_values) != 210:
            errors.append("VALUE: planned learning path must total 210 minutes")
        session_totals = (
            (
                sum(minute_values[:4]),
                sum(minute_values[4:8]),
                sum(minute_values[8:11]),
                sum(minute_values[11:]),
            )
            if len(minute_values) == 12 and all(type(value) is int for value in minute_values)
            else ()
        )
        if session_totals and session_totals != (50, 65, 50, 45):
            errors.append("VALUE: planned session totals must be 50/65/50/45 minutes")

    for outcome_id, outcome in outcome_by_id.items():
        outcome_steps = outcome.get("steps")
        if not isinstance(outcome_steps, list):
            continue
        for step_number in outcome_steps:
            if type(step_number) is int and 1 <= step_number <= len(steps):
                referenced_step = steps[step_number - 1]
                if not isinstance(referenced_step, dict):
                    continue
                step_outcomes = referenced_step.get("outcome_ids", [])
                if not isinstance(step_outcomes, list):
                    continue
                if outcome_id not in step_outcomes:
                    errors.append(
                        f"RELATION: {outcome_id} names step {step_number}, but the step omits it"
                    )
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        step_outcome_ids = step.get("outcome_ids")
        if not isinstance(step_outcome_ids, list):
            continue
        for outcome_id in step_outcome_ids:
            outcome = outcome_by_id.get(outcome_id)
            if outcome is None:
                continue
            outcome_steps = outcome.get("steps")
            if isinstance(outcome_steps, list) and index not in outcome_steps:
                errors.append(
                    f"RELATION: step {index} names {outcome_id}, but the outcome omits it"
                )

    _pilot_errors(document["pilot"], errors)
    _rubric_errors(document["rubric"], errors)
    return errors


def _pilot_errors(pilot: Any, errors: list[str]) -> None:
    expected_keys = frozenset(
        {
            "authorization",
            "educator_completed",
            "educator_recruited",
            "educator_target",
            "gates",
            "novice_completed",
            "novice_recruited",
            "novice_target",
            "results",
            "status",
        }
    )
    if not _exact_keys(pilot, expected_keys, "pilot", errors):
        return
    assert isinstance(pilot, dict)
    expected_scalars = {
        "authorization": "not-authorized",
        "educator_completed": 0,
        "educator_recruited": 0,
        "educator_target": 1,
        "novice_completed": 0,
        "novice_recruited": 0,
        "novice_target": 6,
        "status": "not-run",
    }
    for key, expected in expected_scalars.items():
        if not _typed_equal(pilot[key], expected):
            errors.append(f"VALUE: pilot.{key} must remain {expected!r}")
    gates = pilot["gates"]
    actual_gates: dict[str, str] = {}
    if not isinstance(gates, list) or len(gates) != len(EXPECTED_GATES):
        errors.append(f"COUNT: pilot.gates must contain exactly {len(EXPECTED_GATES)} rows")
    else:
        for index, gate in enumerate(gates, start=1):
            if not _exact_keys(
                gate, frozenset({"id", "threshold"}), f"pilot.gates[{index}]", errors
            ):
                continue
            assert isinstance(gate, dict)
            if not isinstance(gate["id"], str) or not isinstance(gate["threshold"], str):
                errors.append(f"TYPE: pilot.gates[{index}] values must be strings")
                continue
            if gate["id"] in actual_gates:
                errors.append(f"DUPLICATE: pilot gate {gate['id']}")
            actual_gates[gate["id"]] = gate["threshold"]
        if actual_gates != EXPECTED_GATES:
            errors.append("VALUE: pilot gate IDs or thresholds drifted")
    results = pilot["results"]
    if _exact_keys(results, EXPECTED_RESULT_KEYS, "pilot.results", errors):
        assert isinstance(results, dict)
        if any(value is not None for value in results.values()):
            errors.append("VALUE: unrun pilot results must all be null")


def _rubric_errors(rubric: Any, errors: list[str]) -> None:
    if not _exact_keys(
        rubric,
        frozenset({"aggregation", "dimensions", "not_assessed", "score_values", "use"}),
        "rubric",
        errors,
    ):
        return
    assert isinstance(rubric, dict)
    if rubric["aggregation"] != "no-total-score":
        errors.append("VALUE: rubric.aggregation must forbid a total score")
    if rubric["use"] != "formative-not-canonical-completion-or-g4":
        errors.append("VALUE: rubric.use must preserve the formative-only boundary")
    if not _typed_equal(rubric["score_values"], [0, 1, 2, 3]):
        errors.append("VALUE: rubric.score_values must be exact integers 0..3")
    if (
        not isinstance(rubric["not_assessed"], str)
        or "do not convert" not in rubric["not_assessed"]
    ):
        errors.append("VALUE: rubric.not_assessed must keep missing evidence separate from score 0")
    dimensions = rubric["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) != 4:
        errors.append("COUNT: rubric.dimensions must contain exactly 4 rows")
        return
    ids: list[str] = []
    for index, dimension in enumerate(dimensions, start=1):
        context = f"rubric.dimensions[{index}]"
        if not _exact_keys(dimension, RUBRIC_DIMENSION_KEYS, context, errors):
            continue
        assert isinstance(dimension, dict)
        ids.append(dimension["id"] if isinstance(dimension["id"], str) else "")
        if not isinstance(dimension["name"], str) or not dimension["name"].strip():
            errors.append(f"TYPE: {context}.name must be non-empty")
        outcome_ids = _string_list(dimension["outcome_ids"], f"{context}.outcome_ids", errors)
        if any(outcome_id not in EXPECTED_OUTCOME_STEPS for outcome_id in outcome_ids):
            errors.append(f"VALUE: {context}.outcome_ids contains an unknown outcome")
        levels = dimension["levels"]
        if not _exact_keys(levels, frozenset({"0", "1", "2", "3"}), f"{context}.levels", errors):
            continue
        assert isinstance(levels, dict)
        if any(not isinstance(value, str) or not value.strip() for value in levels.values()):
            errors.append(f"TYPE: {context}.levels must contain non-empty strings")
    if ids != ["R-01", "R-02", "R-03", "R-04"]:
        errors.append("ORDER: rubric dimensions must be R-01 through R-04")


def _assignment(tree: ast.Module, name: str) -> ast.AST:
    matches: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            matches.append(node.value)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            matches.append(node.value)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one assignment for {name}, found {len(matches)}")
    return matches[0]


def _literal_call_records(
    tree: ast.Module,
    name: str,
    constructor: str,
    *,
    named_literals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    value = _assignment(tree, name)
    if not isinstance(value, (ast.Tuple, ast.List)):
        raise ValueError(f"{name} must be a literal sequence")
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value.elts, start=1):
        if (
            not isinstance(item, ast.Call)
            or not isinstance(item.func, ast.Name)
            or item.func.id != constructor
        ):
            raise ValueError(f"{name}[{index}] must call {constructor}")
        if item.args or any(keyword.arg is None for keyword in item.keywords):
            raise ValueError(f"{name}[{index}] must use literal named arguments")
        record: dict[str, Any] = {}
        for keyword in item.keywords:
            assert keyword.arg is not None
            if keyword.arg in record:
                raise ValueError(f"{name}[{index}] repeats {keyword.arg}")
            if isinstance(keyword.value, ast.Name) and named_literals is not None:
                try:
                    record[keyword.arg] = named_literals[keyword.value.id]
                except KeyError as exc:
                    raise ValueError(
                        f"{name}[{index}] uses unknown literal name {keyword.value.id}"
                    ) from exc
            else:
                record[keyword.arg] = ast.literal_eval(keyword.value)
        records.append(record)
    return records


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    return ast.literal_eval(_assignment(tree, name))


def _scenario_id(lab_name: str, config_path: str) -> str:
    prefix = {
        "lab01_msd": "lab01",
        "lab02_pid": "lab02",
        "lab03_trajectory": "lab03",
        "lab03_2dof": "lab03",
        "lab04_panda": "lab04",
    }.get(lab_name, lab_name)
    slug = re.sub(r"[^a-z0-9]+", "-", Path(config_path).stem.lower()).strip("-")
    return f"{prefix}.{slug}"


def _expression_matches(node: ast.AST | None, expression: str) -> bool:
    if node is None:
        return False
    expected = ast.parse(expression, mode="eval").body
    return ast.dump(node, include_attributes=False) == ast.dump(
        expected,
        include_attributes=False,
    )


def _named_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one function {name}, found {len(matches)}")
    return matches[0]


def _named_class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    classes = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise ValueError(f"expected exactly one class {class_name}, found {len(classes)}")
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    ]
    if len(methods) != 1:
        raise ValueError(f"expected exactly one {class_name}.{method_name}, found {len(methods)}")
    return methods[0]


def _call_keywords(call: ast.Call) -> dict[str, ast.AST]:
    if call.args or any(keyword.arg is None for keyword in call.keywords):
        raise ValueError("completion declarations must use named arguments")
    result: dict[str, ast.AST] = {}
    for keyword in call.keywords:
        assert keyword.arg is not None
        if keyword.arg in result:
            raise ValueError(f"completion declaration repeats {keyword.arg}")
        result[keyword.arg] = keyword.value
    return result


def _scenario_completion_source_errors(catalog_tree: ast.Module) -> list[str]:
    errors: list[str] = []
    try:
        default_method = _named_class_method(catalog_tree, "ScenarioCatalog", "default")
        scenario_calls = [
            node
            for node in ast.walk(default_method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ScenarioDefinition"
        ]
        if len(scenario_calls) != 1:
            return [
                "SOURCE_DRIFT: ScenarioCatalog.default must contain one ScenarioDefinition template"
            ]
        definition_keywords = _call_keywords(scenario_calls[0])
        completion = definition_keywords.get("completion")
        if (
            not isinstance(completion, ast.Call)
            or not isinstance(completion.func, ast.Name)
            or completion.func.id != "CompletionRule"
        ):
            return ["SOURCE_DRIFT: ScenarioCatalog.default completion rule is missing"]
        keywords = _call_keywords(completion)
        expected_keys = {
            "requires_plot",
            "requires_learner_control",
            "requires_observation",
            "requires_prediction",
            "requires_note",
            "required_presets",
        }
        if set(keywords) != expected_keys:
            errors.append("SOURCE_DRIFT: scenario CompletionRule fields drifted")
        if not _expression_matches(keywords.get("requires_plot"), "True"):
            errors.append("SOURCE_DRIFT: scenario CompletionRule requires_plot drifted")
        for field in (
            "requires_learner_control",
            "requires_observation",
            "requires_prediction",
            "requires_note",
        ):
            if not _expression_matches(keywords.get(field), "interactive"):
                errors.append(f"SOURCE_DRIFT: scenario CompletionRule {field} drifted")
        if not _expression_matches(
            keywords.get("required_presets"),
            "_required_preset_labels(config)",
        ):
            errors.append("SOURCE_DRIFT: scenario CompletionRule required_presets drifted")
    except (SyntaxError, ValueError, TypeError) as exc:
        errors.append(f"SOURCE_PARSE: scenario completion: {exc}")
    return errors


def _batch_completion_source_errors(catalog_tree: ast.Module) -> list[str]:
    errors: list[str] = []
    try:
        concrete_names = tuple(_literal_assignment(catalog_tree, "CONCRETE_BATCH_NAMES"))
        if tuple(f"batch.{name}" for name in concrete_names) != EXPECTED_CONCRETE_BATCH_TARGET_IDS:
            errors.append("SOURCE_DRIFT: concrete batch target IDs drifted")
        if not _expression_matches(
            _assignment(catalog_tree, "CONCRETE_BATCH_TARGET_IDS"),
            'tuple(f"batch.{name}" for name in CONCRETE_BATCH_NAMES)',
        ):
            errors.append("SOURCE_DRIFT: CONCRETE_BATCH_TARGET_IDS construction drifted")

        function = _named_function(catalog_tree, "_default_batch_definitions")
        calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "BatchDefinition"
        ]
        if len(calls) != 2:
            return [
                *errors,
                "SOURCE_DRIFT: _default_batch_definitions must declare concrete and course rules",
            ]
        records = [_call_keywords(call) for call in calls]
        course = next(
            (
                record
                for record in records
                if _expression_matches(record.get("id"), "ALL_BATCH_TARGET_ID")
            ),
            None,
        )
        concrete = next((record for record in records if record is not course), None)
        if concrete is None or course is None:
            return [*errors, "SOURCE_DRIFT: batch rule identities drifted"]
        if not _expression_matches(
            concrete.get("child_target_ids"),
            "tuple(stable_scenario_id(item.lab_name, item.config_path) for item in BATCH_SETS[batch_name])",
        ):
            errors.append("SOURCE_DRIFT: concrete batch child-target derivation drifted")
        if not _expression_matches(
            concrete.get("completion"),
            "CompletionRule(requires_plot=True, required_artifacts=(REPORT_ARTIFACT_KEY, WORKSHEET_ARTIFACT_KEY, PREDICTION_CHECK_ARTIFACT_KEY))",
        ):
            errors.append("SOURCE_DRIFT: concrete batch CompletionRule drifted")
        if not _expression_matches(course.get("child_target_ids"), "CONCRETE_BATCH_TARGET_IDS"):
            errors.append("SOURCE_DRIFT: course batch child targets drifted")
        if not _expression_matches(
            course.get("completion"),
            "CompletionRule(required_artifacts=(REPORT_ARTIFACT_KEY, WORKSHEET_ARTIFACT_KEY, *CONCRETE_BATCH_TARGET_IDS))",
        ):
            errors.append("SOURCE_DRIFT: course batch CompletionRule drifted")
    except (SyntaxError, ValueError, TypeError) as exc:
        errors.append(f"SOURCE_PARSE: batch completion: {exc}")
    return errors


def _clean_yaml_scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text.split(" #", 1)[0].strip()


def _yaml_truthy(value: str) -> bool:
    text = _clean_yaml_scalar(value).casefold()
    return text not in {"", "0", "false", "no", "null", "none", "off", "~"}


def _interaction_contract(config_text: str) -> tuple[bool, tuple[str, ...]]:
    interaction_indent: int | None = None
    flags: dict[str, bool] = {}
    presets: list[dict[str, str]] = []
    current_preset: dict[str, str] | None = None
    for raw_line in config_text.splitlines():
        content = raw_line.lstrip(" ")
        if not content or content.startswith("#"):
            continue
        indent = len(raw_line) - len(content)
        if interaction_indent is None:
            if content == "interaction:":
                interaction_indent = indent
            continue
        if indent <= interaction_indent:
            break
        stripped = content.strip()
        if indent == interaction_indent + 2 and ":" in stripped:
            key, value = stripped.split(":", 1)
            if key in {"panel", "live_tuning", "key_force"}:
                flags[key] = _yaml_truthy(value)
        if indent == interaction_indent + 4 and stripped.startswith("- "):
            if current_preset is not None:
                presets.append(current_preset)
            current_preset = {}
            stripped = stripped[2:].strip()
        if current_preset is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.removeprefix("- ").strip()
            if key in {"label", "name", "required"}:
                current_preset[key] = _clean_yaml_scalar(value)
    if current_preset is not None:
        presets.append(current_preset)
    required = tuple(
        preset.get("label") or preset.get("name") or f"Preset {index}"
        for index, preset in enumerate(presets, start=1)
        if _yaml_truthy(preset.get("required", ""))
    )
    return any(flags.values()), required


def _config_source_errors(
    root: Path,
    config_path: str,
    *,
    target_id: str,
    expected_mode: str,
    expected_presets: tuple[str, ...],
) -> list[str]:
    text, error = _safe_read(root, Path(config_path))
    if error or text is None:
        return [error or f"MISSING_FILE: {config_path}"]
    expected_hash = CONFIG_SHA256.get(config_path)
    if expected_hash is None:
        return [f"SOURCE_DRIFT: {target_id} config is outside the reviewed path set"]
    interactive, required_presets = _interaction_contract(text)
    errors: list[str] = []
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected_hash:
        errors.append(f"HASH_DRIFT: {config_path} differs from the reviewed path config")
    if interactive != (expected_mode == "hands-on"):
        errors.append(f"SOURCE_DRIFT: {target_id} interaction mode differs from the kit")
    if required_presets != expected_presets:
        errors.append(f"SOURCE_DRIFT: {target_id} required preset labels/order drifted")
    return errors


def _source_errors(root: Path, document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    menu_text, menu_error = _safe_read(root, MENU_PATH)
    catalog_text, catalog_error = _safe_read(root, CATALOG_PATH)
    batch_text, batch_error = _safe_read(root, BATCH_PATH)
    config_source_text, config_source_error = _safe_read(root, CONFIG_PATH)
    completion_text, completion_error = _safe_read(root, COMPLETION_PATH)
    if menu_error:
        errors.append(menu_error)
    if catalog_error:
        errors.append(catalog_error)
    if batch_error:
        errors.append(batch_error)
    if config_source_error:
        errors.append(config_source_error)
    if completion_error:
        errors.append(completion_error)
    if (
        menu_text is None
        or catalog_text is None
        or batch_text is None
        or config_source_text is None
        or completion_text is None
    ):
        return errors
    if hashlib.sha256(catalog_text.encode("utf-8")).hexdigest() != CATALOG_SOURCE_SHA256:
        errors.append("HASH_DRIFT: ScenarioCatalog source differs from the reviewed contract")
    if hashlib.sha256(config_source_text.encode("utf-8")).hexdigest() != CONFIG_SOURCE_SHA256:
        errors.append("HASH_DRIFT: config loader source differs from the reviewed contract")
    if hashlib.sha256(completion_text.encode("utf-8")).hexdigest() != COMPLETION_SOURCE_SHA256:
        errors.append("SOURCE_DRIFT: CompletionRule/evaluate_completion source drifted")
    try:
        menu_tree = ast.parse(menu_text, filename=str(MENU_PATH))
        catalog_tree = ast.parse(catalog_text, filename=str(CATALOG_PATH))
        batch_tree = ast.parse(batch_text, filename=str(BATCH_PATH))
        all_batch_name = _literal_assignment(batch_tree, "ALL_BATCH_NAME")
        path_records = _literal_call_records(menu_tree, "LEARNING_PATH", "LearningPathStep")
        menu_actions = _literal_call_records(menu_tree, "MENU_ACTIONS", "MenuAction")
        batch_actions = _literal_call_records(
            menu_tree,
            "BATCH_ACTIONS",
            "BatchMenuAction",
            named_literals={"ALL_BATCH_NAME": all_batch_name},
        )
        scenario_ids = tuple(_literal_assignment(catalog_tree, "LEARNING_PATH_SCENARIO_IDS"))
        all_batch_id = _literal_assignment(catalog_tree, "ALL_BATCH_TARGET_ID")
    except (SyntaxError, ValueError, TypeError) as exc:
        errors.append(f"SOURCE_PARSE: {exc}")
        return errors

    expected_source_targets = (*scenario_ids, all_batch_id)
    if expected_source_targets != EXPECTED_TARGET_IDS:
        errors.append("SOURCE_DRIFT: catalog LEARNING_PATH_TARGET_IDS inputs drifted")
    if not _expression_matches(
        _assignment(catalog_tree, "LEARNING_PATH_TARGET_IDS"),
        "(*LEARNING_PATH_SCENARIO_IDS, ALL_BATCH_TARGET_ID)",
    ):
        errors.append("SOURCE_DRIFT: LEARNING_PATH_TARGET_IDS declaration drifted")
    errors.extend(_scenario_completion_source_errors(catalog_tree))
    errors.extend(_batch_completion_source_errors(catalog_tree))
    if len(path_records) != 12:
        errors.append(f"SOURCE_DRIFT: LEARNING_PATH has {len(path_records)} rows, expected 12")
        return errors
    kit_steps = document.get("learning_path")
    if not isinstance(kit_steps, list) or len(kit_steps) != 12:
        return errors

    for index, (path_record, kit_step) in enumerate(
        zip(path_records, kit_steps, strict=True), start=1
    ):
        if not isinstance(kit_step, dict):
            continue
        for key in ("title", "action_kind", "group", "label", "description"):
            if path_record.get(key) != kit_step.get(key):
                errors.append(
                    f"SOURCE_DRIFT: learning_path[{index}].{key} differs from LEARNING_PATH"
                )
        matches = [
            action
            for action in (
                batch_actions if path_record.get("action_kind") == "batch" else menu_actions
            )
            if action.get("group") == path_record.get("group")
            and action.get("label") == path_record.get("label")
        ]
        if len(matches) != 1:
            errors.append(
                f"SOURCE_DRIFT: path row {index} resolves to {len(matches)} executable actions"
            )
            continue
        action = matches[0]
        if path_record.get("action_kind") == "batch":
            target_id = f"batch.{action.get('batch_name')}"
            command = f"python -m mclab batch {action.get('batch_name')} --open-report"
        else:
            lab_name = action.get("lab_name")
            config_path = action.get("config_path")
            plots = action.get("plots")
            if not all(
                isinstance(value, str) and value for value in (lab_name, config_path, plots)
            ):
                errors.append(f"SOURCE_DRIFT: path row {index} has an incomplete MenuAction")
                continue
            target_id = _scenario_id(lab_name, config_path)
            mode_flags = (
                "--viewer --realtime --pause-at-end"
                if target_id in HANDS_ON_TARGET_IDS
                else "--headless"
            )
            command = (
                f"python -m mclab run {lab_name} --config {config_path} {mode_flags} "
                f"--plot --plots {plots} --open-report"
            )
            expected_presets = ()
            canonical = kit_step.get("canonical_completion_evidence")
            if isinstance(canonical, dict):
                raw_presets = canonical.get("required_presets")
                if isinstance(raw_presets, list) and all(
                    isinstance(item, str) for item in raw_presets
                ):
                    expected_presets = tuple(raw_presets)
            expected_mode = str(kit_step.get("mode") or "")
            errors.extend(
                _config_source_errors(
                    root,
                    config_path,
                    target_id=target_id,
                    expected_mode=expected_mode,
                    expected_presets=expected_presets,
                )
            )
        if kit_step.get("target_id") != target_id:
            errors.append(
                f"SOURCE_DRIFT: learning_path[{index}].target_id is not executable action ID"
            )
        if kit_step.get("command") != command:
            errors.append(
                f"SOURCE_DRIFT: learning_path[{index}].command is not the canonical command"
            )
        if target_id != expected_source_targets[index - 1]:
            errors.append(f"SOURCE_DRIFT: executable path row {index} differs from catalog order")

    return errors


def _schema_errors(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["TYPE: educator schema must be an object"]
    if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("VALUE: educator schema draft drifted")
    if document.get("type") != "object" or document.get("additionalProperties") is not False:
        errors.append("VALUE: educator schema root must be a closed object")
    properties = document.get("properties")
    if not isinstance(properties, dict) or frozenset(properties) != TOP_LEVEL_KEYS:
        errors.append("VALUE: educator schema top-level properties drifted")
    required = document.get("required")
    if not isinstance(required, list) or frozenset(required) != TOP_LEVEL_KEYS:
        errors.append("VALUE: educator schema required fields drifted")
    definitions = document.get("$defs")
    if not isinstance(definitions, dict):
        errors.append("TYPE: educator schema $defs must be an object")
        return errors
    expected_definitions = {
        "canonicalCompletionEvidence",
        "canonicalSources",
        "gate",
        "learningOutcome",
        "levels",
        "pathStep",
        "pilot",
        "results",
        "rubric",
        "rubricDimension",
        "scope",
        "unresolvedDecision",
    }
    if set(definitions) != expected_definitions:
        errors.append("VALUE: educator schema definitions drifted")
    for name, definition in definitions.items():
        if not isinstance(definition, dict):
            errors.append(f"TYPE: schema definition {name} must be an object")
            continue
        props = definition.get("properties")
        if props is not None:
            if (
                definition.get("type") != "object"
                or definition.get("additionalProperties") is not False
            ):
                errors.append(f"VALUE: schema definition {name} must be a closed object")
            if not isinstance(props, dict) or set(definition.get("required", [])) != set(props):
                errors.append(f"VALUE: schema definition {name} must require every property")

    def walk_json(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and not reference.startswith("#/$defs/"):
                errors.append(f"VALUE: external schema reference is forbidden: {reference}")
            for child in value.values():
                walk_json(child)
        elif isinstance(value, list):
            for child in value:
                walk_json(child)

    walk_json(document)
    return errors


def _claim_statements(text: str) -> tuple[str, ...]:
    candidates: list[str] = []
    paragraph_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if paragraph_lines:
                candidates.append(" ".join(paragraph_lines))
                paragraph_lines = []
            continue
        starts_block = bool(re.match(r"^(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)", line))
        if starts_block and paragraph_lines:
            candidates.append(" ".join(paragraph_lines))
            paragraph_lines = []
        paragraph_lines.append(line)
    if paragraph_lines:
        candidates.append(" ".join(paragraph_lines))

    statements: dict[str, None] = {}
    for candidate in candidates:
        for fragment in re.split(
            r"[.!?;:]+|\b(?:and|but|however|yet)\b",
            candidate,
            flags=re.IGNORECASE,
        ):
            normalized = re.sub(r"[`*_#>|\[\](){}]", " ", fragment)
            normalized = " ".join(normalized.split()).strip(" -:")
            if normalized:
                statements.setdefault(normalized, None)
    return tuple(statements)


def _forbidden_claim_errors(relative: Path, text: str) -> list[str]:
    errors: list[str] = []
    for statement in _claim_statements(text):
        if CLAIM_CONDITIONAL_PREFIX_RE.search(statement):
            continue
        for category, pattern in FORBIDDEN_CLAIM_PATTERNS:
            match = pattern.search(statement)
            if match is None:
                continue
            local_context = statement[max(0, match.start() - 96) : match.end()]
            if CLAIM_NEGATION_RE.search(local_context):
                continue
            excerpt = statement if len(statement) <= 180 else f"{statement[:177]}..."
            errors.append(f"SEMANTIC_OVERCLAIM[{category}]: {relative}: {excerpt}")
    return errors


def _documentation_errors(root: Path, document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    texts: dict[Path, str] = {}
    for relative in (GUIDE_PATH, PILOT_PATH, DOC_MAP_PATH):
        raw, error = _safe_read_bytes(root, relative)
        if error:
            errors.append(error)
            continue
        assert raw is not None
        expected_hash = DOCUMENT_SHA256[relative]
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            errors.append(f"HASH_DRIFT: {relative} differs from the approved documentation bytes")
        text, decode_error = _decode_utf8(raw, relative)
        if decode_error:
            errors.append(decode_error)
        elif text is not None:
            texts[relative] = text
            errors.extend(_forbidden_claim_errors(relative, text))
    guide = texts.get(GUIDE_PATH, "")
    pilot = texts.get(PILOT_PATH, "")
    doc_map = texts.get(DOC_MAP_PATH, "")
    normalized_guide = " ".join(guide.split())
    normalized_pilot = " ".join(pilot.split())
    for heading in GUIDE_HEADINGS:
        if f"## {heading}" not in guide:
            errors.append(f"DOC_MARKER: educator guide missing heading {heading!r}")
    for marker in GUIDE_MARKERS:
        if marker not in normalized_guide:
            errors.append(f"DOC_MARKER: educator guide missing {marker!r}")
    for command in HEADLESS_FALLBACK_COMMANDS:
        if command not in guide:
            errors.append(f"DOC_COMMAND: educator guide omits headless fallback {command!r}")
    for heading in PILOT_HEADINGS:
        if f"## {heading}" not in pilot:
            errors.append(f"DOC_MARKER: pilot protocol missing heading {heading!r}")
    for marker in PILOT_MARKERS:
        if marker not in normalized_pilot:
            errors.append(f"DOC_MARKER: pilot protocol missing {marker!r}")
    documented_steps = document.get("learning_path")
    if not isinstance(documented_steps, list):
        documented_steps = []
    for step in documented_steps:
        if isinstance(step, dict) and isinstance(step.get("command"), str):
            if step["command"] not in guide:
                errors.append(
                    f"DOC_COMMAND: educator guide omits {step.get('target_id', '<unknown>')}"
                )
    for link in ("educator_guide.md", "educator_pilot_protocol.md", "educator_kit.json"):
        if f"({link})" not in doc_map:
            errors.append(f"DOC_LINK: docs map omits {link}")
    for source, text in ((GUIDE_PATH, guide), (PILOT_PATH, pilot)):
        for destination in LOCAL_LINK_RE.findall(text):
            if destination.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_text = destination.split("#", 1)[0]
            if not path_text:
                continue
            target = source.parent / path_text
            _unused, error = _safe_read(root, target)
            if error:
                errors.append(f"BROKEN_LINK: {source} -> {destination}: {error}")
    return errors


def _checked_errors(label: str, operation: Callable[[], list[str]]) -> list[str]:
    try:
        result = operation()
    except Exception as exc:  # validation must report a controlled failure
        return [f"VALIDATION_EXCEPTION: {label}: {exc.__class__.__name__}: {exc}"]
    if not isinstance(result, list) or any(not isinstance(item, str) for item in result):
        return [f"VALIDATION_EXCEPTION: {label}: validator returned an invalid result"]
    return result


def validate(root: Path = ROOT) -> tuple[list[ValidationMetric], list[str]]:
    errors: list[str] = []
    kit, _kit_text, kit_raw, kit_error = _load_json(root, KIT_PATH)
    schema, _schema_text, schema_raw, schema_error = _load_json(root, SCHEMA_PATH)
    if kit_error:
        errors.append(kit_error)
    if schema_error:
        errors.append(schema_error)
    if kit_raw is not None and hashlib.sha256(kit_raw).hexdigest() != KIT_SHA256:
        errors.append("HASH_DRIFT: educator_kit.json differs from the reviewed contract")
    if schema_raw is not None and hashlib.sha256(schema_raw).hexdigest() != SCHEMA_SHA256:
        errors.append("HASH_DRIFT: educator_kit.schema.json differs from the reviewed contract")
    if kit is not None:
        errors.extend(_checked_errors("educator kit", lambda: _document_errors(kit)))
        if isinstance(kit, dict):
            errors.extend(_checked_errors("source closure", lambda: _source_errors(root, kit)))
            errors.extend(
                _checked_errors(
                    "documentation",
                    lambda: _documentation_errors(root, kit),
                )
            )
    if schema is not None:
        errors.extend(_checked_errors("schema", lambda: _schema_errors(schema)))
    metrics = [
        ValidationMetric("learning_path_steps", 12),
        ValidationMetric("learning_outcomes", 5),
        ValidationMetric("planned_minutes", 210),
        ValidationMetric("pilot_status", "not-run"),
        ValidationMetric("human_evidence", 0),
    ]
    return metrics, errors


def _print_document_hashes(root: Path) -> int:
    """Print bounded raw-byte hashes for an explicitly reviewed document rebind."""

    lines: list[str] = []
    errors: list[str] = []
    for relative in DOCUMENT_SHA256:
        raw, error = _safe_read_bytes(root, relative)
        if error or raw is None:
            errors.append(error or f"READ_ERROR: {relative}")
            continue
        document_text, decode_error = _decode_utf8(raw, relative)
        if decode_error or document_text is None:
            errors.append(decode_error or f"INVALID_UTF8: {relative}")
            continue
        errors.extend(_forbidden_claim_errors(relative, document_text))
        lines.append(f"{relative}: {hashlib.sha256(raw).hexdigest()}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = ROOT
    print_document_hashes = False
    if "--print-document-hashes" in args:
        if args.count("--print-document-hashes") != 1:
            print("usage: check_educator_kit.py [--root PATH] [--print-document-hashes]")
            return 2
        args.remove("--print-document-hashes")
        print_document_hashes = True
    if args:
        if len(args) != 2 or args[0] != "--root":
            print("usage: check_educator_kit.py [--root PATH] [--print-document-hashes]")
            return 2
        root = Path(args[1])
    if print_document_hashes:
        return _print_document_hashes(root)
    metrics, errors = validate(root)
    for metric in metrics:
        print(f"{metric.name}: {metric.value}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print("status: FAIL")
        return 1
    print("status: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
