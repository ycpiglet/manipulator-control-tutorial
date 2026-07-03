"""Portable citation/provenance coverage check for the paper.

Replaces the PowerShell snippet in paper/README.md with a cross-platform
script usable both locally and in CI. Pure standard library on purpose.

Gates enforced (exit code 1 on any failure):
- every citation key used in paper/sections/*.tex and paper/main.tex exists
  in paper/references/refs.bib
- every used key exists in the paper/references/sources.md provenance table
- refs.bib contains no duplicate entry keys

Unused BibTeX entries are reported as information only; the repository keeps
some entries intentionally for later related-work expansion.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"

CITE_RE = re.compile(r"\\cite\{([^}]+)\}")
BIB_KEY_RE = re.compile(r"^@[a-zA-Z]+\{([^,\s]+)", re.MULTILINE)
MANIFEST_KEY_RE = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)


def used_keys() -> set[str]:
    keys: set[str] = set()
    tex_files = sorted((PAPER / "sections").glob("*.tex")) + [PAPER / "main.tex"]
    for tex in tex_files:
        for group in CITE_RE.findall(tex.read_text(encoding="utf-8")):
            keys.update(key.strip() for key in group.split(",") if key.strip())
    return keys


def bib_keys() -> list[str]:
    text = (PAPER / "references" / "refs.bib").read_text(encoding="utf-8")
    return BIB_KEY_RE.findall(text)


def manifest_keys() -> set[str]:
    text = (PAPER / "references" / "sources.md").read_text(encoding="utf-8")
    return set(MANIFEST_KEY_RE.findall(text))


def main() -> int:
    used = used_keys()
    bib_list = bib_keys()
    bib = set(bib_list)
    manifest = manifest_keys()

    duplicate_bib = sorted({key for key in bib_list if bib_list.count(key) > 1})
    missing_in_bib = sorted(used - bib)
    missing_in_manifest = sorted(used - manifest)
    unused_bib = sorted(bib - used)

    print(f"used citation keys: {len(used)}")
    print(f"bib entries: {len(bib_list)} (unique {len(bib)})")
    print(f"manifest entries: {len(manifest)}")
    print(f"missing in refs.bib: {missing_in_bib or 'none'}")
    print(f"missing in sources.md: {missing_in_manifest or 'none'}")
    print(f"duplicate bib keys: {duplicate_bib or 'none'}")
    print(f"unused bib entries (informational): {unused_bib or 'none'}")

    failed = bool(missing_in_bib or missing_in_manifest or duplicate_bib)
    print("status:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
