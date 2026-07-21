"""Pinned, serialized writes inside one saved-output publication boundary."""

from __future__ import annotations

import hmac
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from mclab.completion import CompletionRecordKind
from mclab.output_inventory import (
    assert_output_tree_mutable_rooted,
    read_json_mapping_rooted,
    validate_completion_manifest_v1,
)
from mclab.output_root import PinnedOutputRoot, pinned_output_root
from mclab.output_safety import (
    MAX_OUTPUT_ROOT_ENTRIES,
    CleanupBusyError,
    CleanupOperationError,
    CleanupSafetyError,
)


class OutputPublicationBusyError(RuntimeError):
    """A bounded publication could not acquire the shared output-root lease."""


@dataclass(frozen=True)
class OutputPublication:
    """Root-relative read/write access while the output directory stays pinned."""

    root: Path
    root_pin: PinnedOutputRoot
    marker_digest: str | None = None

    def path(self, relative: tuple[str, ...]) -> Path:
        return self.root_pin.display_path(relative)

    def read_bytes(
        self,
        relative: tuple[str, ...],
        *,
        description: str,
        max_bytes: int,
        allow_empty: bool = True,
    ) -> bytes:
        return self.root_pin.read_regular_file(
            relative,
            description=description,
            max_bytes=max_bytes,
            allow_empty=allow_empty,
        )

    def regular_file_exists(self, relative: tuple[str, ...]) -> bool:
        try:
            opened = self.root_pin.lstat(relative)
        except FileNotFoundError:
            return False
        return stat.S_ISREG(opened.st_mode) and not stat.S_ISLNK(opened.st_mode)

    def ensure_directory(self, relative: tuple[str, ...], *, mode: int = 0o755) -> None:
        self.assert_running_marker()
        if self.root_pin.lexists(relative):
            self.root_pin.validate_directory(relative, description="publication directory")
            return
        self.root_pin.mkdir(relative, mode=mode)
        self.root_pin.validate_directory(relative, description="publication directory")

    def write_bytes(
        self,
        relative: tuple[str, ...],
        data: bytes,
        *,
        mode: int = 0o644,
    ) -> Path:
        self.assert_running_marker()
        self.root_pin.replace_regular_file(relative, data, mode=mode)
        return self.path(relative)

    def write_text(
        self,
        relative: tuple[str, ...],
        text: str,
        *,
        mode: int = 0o644,
    ) -> Path:
        return self.write_bytes(relative, text.encode("utf-8"), mode=mode)

    def assert_running_marker(self) -> None:
        if self.marker_digest is None:
            if self.root_pin.lexists(("manifest.json",)) or self.root_pin.lexists(
                ("summary.json",)
            ):
                raise CleanupSafetyError(
                    "Collection output became a run-shaped publication before commit"
                )
            return
        payload, digest = read_json_mapping_rooted(
            self.root_pin,
            ("manifest.json",),
            description="publication output manifest",
        )
        validation = validate_completion_manifest_v1(payload)
        if (
            validation.record_kind != CompletionRecordKind.MANIFEST_V1
            or validation.status != "running"
            or not hmac.compare_digest(self.marker_digest, digest)
        ):
            raise CleanupSafetyError("Publication manifest changed before artifact commit")


@contextmanager
def mutable_run_publication(output_path: str | Path) -> Iterator[OutputPublication]:
    """Serialize one run-local write and keep its running manifest unchanged."""

    with _output_publication(output_path, allow_collection=False) as publication:
        yield publication


@contextmanager
def mutable_collection_publication(
    output_path: str | Path,
) -> Iterator[OutputPublication]:
    """Serialize an index write; a run-shaped root must still be running."""

    with _output_publication(output_path, allow_collection=True) as publication:
        yield publication


@contextmanager
def _output_publication(
    output_path: str | Path,
    *,
    allow_collection: bool,
) -> Iterator[OutputPublication]:
    output = Path(os.path.abspath(os.path.expanduser(os.fspath(output_path))))
    try:
        with pinned_output_root(output, allowed_root=output) as (
            root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Publication output directory does not exist")
            root_pin.validate_directory((), description="publication output")
            with root_pin.operation_lock():
                marker_digest = _running_marker_digest(
                    root_pin,
                    allow_collection=allow_collection,
                )
                if marker_digest is not None:
                    assert_output_tree_mutable_rooted(root_pin)
                else:
                    names = root_pin.list_names(
                        max_entries=MAX_OUTPUT_ROOT_ENTRIES,
                    )
                    if (
                        len(names) == MAX_OUTPUT_ROOT_ENTRIES
                        and "index.html" not in names
                    ):
                        raise CleanupSafetyError(
                            "Collection has no bounded slot for index publication"
                        )
                publication = OutputPublication(
                    root=root,
                    root_pin=root_pin,
                    marker_digest=marker_digest,
                )
                completed = False
                try:
                    yield publication
                    completed = True
                finally:
                    if completed:
                        publication.assert_running_marker()
                        root_pin.assert_transaction_boundaries()
    except CleanupBusyError as exc:
        raise OutputPublicationBusyError(
            "Refusing to rewrite artifacts because publication is busy."
        ) from exc
    except (CleanupOperationError, CleanupSafetyError, OSError) as exc:
        raise RuntimeError(
            "Refusing to rewrite artifacts because the output tree is terminal or "
            "unsafe."
        ) from exc


def _running_marker_digest(
    root_pin: PinnedOutputRoot,
    *,
    allow_collection: bool,
) -> str | None:
    has_manifest = root_pin.lexists(("manifest.json",))
    has_summary = root_pin.lexists(("summary.json",))
    if not has_manifest:
        if allow_collection and not has_summary:
            return None
        raise CleanupSafetyError("Publication output has no running manifest")
    payload, digest = read_json_mapping_rooted(
        root_pin,
        ("manifest.json",),
        description="publication output manifest",
    )
    validation = validate_completion_manifest_v1(payload)
    if (
        validation.record_kind != CompletionRecordKind.MANIFEST_V1
        or validation.status != "running"
    ):
        raise CleanupSafetyError("Publication output manifest is not safely mutable")
    return digest
