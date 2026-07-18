#!/usr/bin/env python3
"""Audit rendered MCLab HTML reports with Playwright and axe-core."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, sync_playwright

REPORT_KINDS = {"run", "batch", "course", "index"}
VIEWPORTS = {"desktop": (1280, 720), "mobile": (390, 844)}
AXE_TAGS = (
    "wcag2a",
    "wcag2aa",
    "wcag21a",
    "wcag21aa",
    "wcag22a",
    "wcag22aa",
    "best-practice",
)


@dataclass(frozen=True)
class ReportCase:
    kind: str
    path: Path
    viewport: str
    width: int
    height: int


@dataclass
class ReportResult:
    name: str
    passed: bool
    screenshot: str
    lang: str
    title: str
    h1: str
    horizontal_overflow_px: int
    broken_images: int
    axe_violations: list[dict[str, Any]]
    focus_samples: int
    focus_failures: int
    scroll_regions: int
    inaccessible_scroll_regions: int
    visible_heading_levels: list[int]
    notes: list[str]


def _parse_report(value: str) -> tuple[str, Path]:
    try:
        kind, raw_path = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use KIND=/absolute/path/report.html") from exc
    if kind not in REPORT_KINDS:
        raise argparse.ArgumentTypeError(f"KIND must be one of: {', '.join(sorted(REPORT_KINDS))}")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Report does not exist: {path}")
    return kind, path


def _document_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const visible = element => {
            const style = getComputedStyle(element);
            const box = element.getBoundingClientRect();
            return style.display !== "none" && style.visibility !== "hidden"
                   && box.width > 0 && box.height > 0;
          };
          const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
            .filter(visible).map(element => ({
              level: Number(element.tagName.slice(1)),
              text: element.innerText.trim()
            }));
          const scrollRegions = [...document.querySelectorAll(".table-wrap")].map(element => ({
            overflow: Math.max(0, element.scrollWidth - element.clientWidth),
            tabIndex: element.tabIndex,
            label: element.getAttribute("aria-label") || ""
          }));
          return {
            lang: document.documentElement.lang,
            title: document.title,
            h1: [...document.querySelectorAll("h1")].map(element => element.innerText.trim()),
            headings,
            width: innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            brokenImages: [...document.images]
              .filter(image => !image.complete || image.naturalWidth === 0).length,
            mainCount: document.querySelectorAll("main").length,
            focusableCount: document.querySelectorAll(
              'a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"])'
            ).length,
            scrollRegions,
            advancedOpen: [...document.querySelectorAll("details.advanced")]
              .filter(element => element.open).length,
            priorityTop: document.querySelector(".priority-plot")
              ? document.querySelector(".priority-plot").getBoundingClientRect().top : null,
            keyChanges: document.querySelectorAll(".key-change-grid .key-change").length
          };
        }"""
    )


def _focus_audit(page: Page, count: int) -> tuple[int, int]:
    limit = min(12, count)
    samples = 0
    failures = 0
    seen: set[str] = set()
    page.locator("body").click(position={"x": 1, "y": 1})
    for _ in range(limit):
        page.keyboard.press("Tab")
        state = page.evaluate(
            """() => {
              const element = document.activeElement;
              const style = getComputedStyle(element);
              const box = element.getBoundingClientRect();
              const outline = style.outlineStyle !== "none"
                && parseFloat(style.outlineWidth || "0") > 0;
              const shadow = style.boxShadow && style.boxShadow !== "none";
              return {
                tag: element.tagName,
                signature: element.tagName + "|" + (element.getAttribute("href") || "")
                  + "|" + (element.innerText || "").trim(),
                visible: box.width > 0 && box.height > 0,
                indicated: outline || shadow
              };
            }"""
        )
        if state["tag"] == "BODY" or state["signature"] in seen:
            break
        seen.add(state["signature"])
        samples += 1
        if not state["visible"] or not state["indicated"]:
            failures += 1
    return samples, failures


def _heading_skips(levels: list[int]) -> list[tuple[int, int]]:
    return [
        (before, after)
        for before, after in zip(levels, levels[1:])
        if after > before + 1
    ]


def _run_case(page: Page, axe: Axe, case: ReportCase, output: Path) -> ReportResult:
    name = f"{case.kind}_{case.viewport}"
    screenshot = output / f"{name}.png"
    page.set_viewport_size({"width": case.width, "height": case.height})
    page.goto(case.path.as_uri(), wait_until="load")
    snapshot = _document_snapshot(page)
    axe_response = axe.run(
        page,
        options={
            "runOnly": {"type": "tag", "values": list(AXE_TAGS)},
            "resultTypes": ["violations"],
        },
    ).response
    violations = [
        {
            "id": item["id"],
            "impact": item.get("impact"),
            "nodes": len(item.get("nodes", [])),
            "targets": [node.get("target", []) for node in item.get("nodes", [])],
        }
        for item in axe_response["violations"]
    ]
    focus_samples, focus_failures = _focus_audit(page, int(snapshot["focusableCount"]))
    page.evaluate("document.activeElement.blur(); window.scrollTo(0, 0)")
    page.screenshot(path=str(screenshot), full_page=False)

    notes: list[str] = []
    overflow = max(0, int(snapshot["scrollWidth"]) - case.width)
    h1_values = list(snapshot["h1"])
    h1 = h1_values[0] if h1_values else ""
    heading_levels = [int(item["level"]) for item in snapshot["headings"]]
    scroll_regions = list(snapshot["scrollRegions"])
    inaccessible_regions = sum(
        int(item["overflow"]) > 1 and (int(item["tabIndex"]) < 0 or not item["label"])
        for item in scroll_regions
    )
    if overflow > 1:
        notes.append(f"document overflows horizontally by {overflow}px")
    if int(snapshot["brokenImages"]):
        notes.append(f"{snapshot['brokenImages']} image(s) failed to load")
    if len(h1_values) != 1 or not h1:
        notes.append(f"expected one non-empty h1, found {len(h1_values)}")
    if snapshot["lang"] not in {"ko", "en"}:
        notes.append("html language is not ko or en")
    if int(snapshot["mainCount"]) != 1:
        notes.append(f"expected one main landmark, found {snapshot['mainCount']}")
    if violations:
        notes.append(f"axe found {len(violations)} violation type(s)")
    if focus_samples and focus_failures:
        notes.append(f"{focus_failures}/{focus_samples} sampled Tab stops lack visible focus")
    if inaccessible_regions:
        notes.append(f"{inaccessible_regions} overflowing table region(s) lack keyboard access")
    if skips := _heading_skips(heading_levels):
        notes.append(f"visible heading levels skip: {skips}")
    if case.kind == "run":
        if re.search(r"[_]|\s-\s", h1):
            notes.append("run title exposes a raw identifier")
        if int(snapshot["advancedOpen"]):
            notes.append("advanced details are expanded by default")
        if int(snapshot["keyChanges"]) > 3:
            notes.append("first screen exposes more than three key values")
        priority_top = snapshot["priorityTop"]
        if priority_top is not None and float(priority_top) >= case.height:
            notes.append("priority plot starts below the first viewport")
    return ReportResult(
        name=name,
        passed=not notes,
        screenshot=str(screenshot),
        lang=str(snapshot["lang"]),
        title=str(snapshot["title"]),
        h1=h1,
        horizontal_overflow_px=overflow,
        broken_images=int(snapshot["brokenImages"]),
        axe_violations=violations,
        focus_samples=focus_samples,
        focus_failures=focus_failures,
        scroll_regions=len(scroll_regions),
        inaccessible_scroll_regions=inaccessible_regions,
        visible_heading_levels=heading_levels,
        notes=notes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="append",
        type=_parse_report,
        required=True,
        metavar="KIND=PATH",
        help="Repeat for run, batch, course, or index HTML reports.",
    )
    parser.add_argument("--output", type=Path, default=Path("/tmp/mclab-report-ui-audit"))
    parser.add_argument("--browser-channel", default="chrome")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = [
        ReportCase(kind, path, viewport, width, height)
        for kind, path in args.report
        for viewport, (width, height) in VIEWPORTS.items()
    ]
    results: list[ReportResult] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=args.browser_channel,
            headless=True,
            args=["--allow-file-access-from-files"],
        )
        axe = Axe()
        for case in cases:
            page = browser.new_page(
                viewport={"width": case.width, "height": case.height},
                device_scale_factor=1,
            )
            results.append(_run_case(page, axe, case, args.output))
            page.close()
        browser.close()
    report = {
        "passed": all(item.passed for item in results),
        "thresholds": {
            "horizontal_overflow_px": 1,
            "broken_images": 0,
            "axe_violations": 0,
            "tab_focus_failures": 0,
            "inaccessible_scroll_regions": 0,
            "visible_heading_skips": 0,
        },
        "results": [asdict(item) for item in results],
    }
    destination = args.output / "report_ui_audit.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in results:
        label = "PASS" if item.passed else "FAIL"
        print(
            f"{label} {item.name}: overflow={item.horizontal_overflow_px}px; "
            f"axe={len(item.axe_violations)}; focus={item.focus_failures}/{item.focus_samples}; "
            f"scroll={item.inaccessible_scroll_regions}/{item.scroll_regions}"
        )
        for note in item.notes:
            print(f"  - {note}")
    print(f"Report: {destination}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
