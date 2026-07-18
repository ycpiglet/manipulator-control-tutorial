"""Shared text-entry metrics for deterministic Qt beta probes."""

from __future__ import annotations

from typing import Any


def evidence_text_metrics(root: Any, kind: str, qobject_type: Any) -> dict[str, Any]:
    """Measure one evidence editor and its optional scroll affordance."""

    text_input = root.findChild(qobject_type, f"{kind}Input") if root is not None else None
    scroller = root.findChild(qobject_type, f"{kind}Scroller") if root is not None else None
    scrollbar = (
        root.findChild(qobject_type, f"{kind}VerticalScrollBar")
        if root is not None
        else None
    )

    def metric(name: str, fallback: str) -> float | None:
        if text_input is None:
            return None
        value = text_input.property(name)
        if value is None:
            value = text_input.property(fallback)
        return float(value)

    content_item = scroller.property("contentItem") if scroller is not None else None
    return {
        f"{kind}_content_width": metric("contentWidth", "width"),
        f"{kind}_available_width": (
            float(scroller.property("availableWidth"))
            if scroller is not None
            else metric("availableWidth", "width")
        ),
        f"{kind}_content_height": metric("contentHeight", "height"),
        f"{kind}_available_height": (
            float(scroller.property("availableHeight"))
            if scroller is not None
            else metric("availableHeight", "height")
        ),
        f"{kind}_line_count": (
            int(text_input.property("lineCount") or 1)
            if text_input is not None
            else None
        ),
        f"{kind}_input_length": (
            len(str(text_input.property("text"))) if text_input is not None else None
        ),
        f"{kind}_scroll_position": (
            float(content_item.property("contentY")) if content_item is not None else None
        ),
        f"{kind}_scroll_content_height": (
            float(scroller.property("contentHeight")) if scroller is not None else None
        ),
        f"{kind}_scrollbar_visible": (
            bool(scrollbar.property("visible")) if scrollbar is not None else None
        ),
        f"{kind}_scrollbar_size": (
            float(scrollbar.property("size")) if scrollbar is not None else None
        ),
    }
