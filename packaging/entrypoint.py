"""PyInstaller entry point that preserves the ``mclab`` package context."""

from mclab.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
