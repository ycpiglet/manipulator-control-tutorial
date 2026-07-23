"""PyInstaller entry point that preserves the ``mclab`` package context."""

from __future__ import annotations

import sys

from mclab.application.batch_worker import ensure_standard_streams


def _main() -> int:
    # A Windows ``console=False`` PyInstaller process can expose ``None`` for
    # one or more standard streams.  Install process-lifetime null streams
    # before importing the CLI: imports and diagnostics may legitimately touch
    # them even when the learner launched the GUI without a console.
    ensure_standard_streams()
    arguments = sys.argv[1:]
    if arguments[:1] == ["__batch-worker"]:
        from mclab.application.batch_worker import main as batch_worker_main

        return batch_worker_main(arguments[1:])

    from mclab.cli import main

    return main(arguments)


if __name__ == "__main__":
    raise SystemExit(_main())
