# Installation and release

## Source setup

Use Python 3.10 or newer. The desktop extra pins `PySide6-Essentials==6.11.1`; the base install remains Qt-free for headless use.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[app]'
python -m mclab assets install
python -m mclab app --self-test
```

`assets install` downloads the pinned MuJoCo Menagerie commit, verifies SHA-256, extracts only `franka_emika_panda`, and preserves its license.

## OS launchers

- Windows: `START_HERE.cmd`
- Linux: `start_here.sh`
- macOS: `START_HERE.command`

All three call `scripts/start_mclab.py`.

## Release policy

Build one-folder applications separately on Windows 11 x64, Ubuntu 24.04 x64, and macOS arm64/Intel. Windows signing and macOS notarization are production gates. CI artifacts are explicitly unsigned development builds.

Target compressed release size: 300 MB or less. Target installed cold start p95: 5 seconds or less.
