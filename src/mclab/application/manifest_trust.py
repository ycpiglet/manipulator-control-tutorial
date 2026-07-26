"""Narrow trust transition for derived report documents."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from mclab.output_root import PinnedOutputRoot
from mclab.output_safety import CleanupSafetyError

REPORT_DOCUMENT_ARTIFACTS = frozenset({"report.html", "worksheet.md"})


def validate_expected_root_identity(
    root_pin: PinnedOutputRoot,
    expected: Mapping[str, int | str] | None,
) -> None:
    """Bind a manifest publication to a previously authenticated physical root."""

    if expected is None:
        return
    if not isinstance(expected, Mapping):
        raise CleanupSafetyError("Expected manifest output identity is invalid")
    observed = root_pin.identity_payload(include_mtime=False)
    if set(expected) != set(observed) or any(
        type(expected[key]) is not type(value) or expected[key] != value
        for key, value in observed.items()
    ):
        raise CleanupSafetyError("Manifest output root identity changed")


def validate_running_document_deferral(
    requested_artifacts: Collection[str],
    *,
    status: str,
) -> frozenset[str]:
    values = tuple(requested_artifacts)
    if any(not isinstance(relative, str) for relative in values):
        raise CleanupSafetyError("Untrusted artifact paths must be strings")
    requested = frozenset(values)
    if requested and status != "running":
        raise CleanupSafetyError(
            "Artifact trust may be deferred only by a running manifest"
        )
    if requested and requested != REPORT_DOCUMENT_ARTIFACTS:
        raise CleanupSafetyError(
            "A running manifest must defer report.html and worksheet.md together"
        )
    return requested
