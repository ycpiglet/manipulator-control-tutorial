# Installation and release

## Source setup

Use CPython 3.10, 3.11, or 3.12. Third-party packages come from committed,
hash-locked, binary-only requirement profiles. The local source is installed
separately without dependency resolution or build isolation.

```bash
python -m venv .venv
source .venv/bin/activate
python scripts/install_locked.py app
python -m mclab assets install
python -m mclab app --self-test
```

Use `runtime` for Qt-free headless labs, `dev` for Qt-free tests and lint,
`app-dev` for desktop development, or `package` for unsigned development
bundles. The installer promotes compatible profiles (for example, `app` plus
`dev` becomes `app-dev`) and validates the environment before a no-op.

The desktop dependency-lock targets are Windows 10 version 1809 or newer and
Windows 11 on AMD64, Linux x86-64 with glibc 2.34 or newer, and macOS 13 or
newer on arm64 or x86-64. This is not a complete native compatibility
certification matrix: all three OS families run CPython 3.11 in CI, Linux
headless CI also runs 3.10 and 3.12, and the remaining cells currently have
cross-target wheel validation only. Other platforms are rejected before
dependency download. Headless `runtime` and `dev` profiles remain Qt-free and
support glibc 2.28 or newer on Linux and macOS 11 or newer; they still use the
reviewed OS/architecture lock targets.

### Dependency trust boundary

The hash locks authenticate downloaded Python wheels and the saved lock state
detects later changes to installed wheel files and editable-loader metadata.
This is an integrity check, not a sandbox: the host OS, the selected CPython
installation, its `venv`/`ensurepip` seed, and the local filesystem before
Python starts are trust roots. Python processes `.pth` and `sitecustomize.py`
before `install_locked.py` can run. If `.venv` may have been modified by an
untrusted local process, remove it and create a new one from a trusted CPython;
the installer deliberately refuses automatic repair when recorded state or
RECORD integrity is invalid.

The Linux desktop workflow also installs its Qt/XCB system libraries from the
signed current Ubuntu repositories. Those apt packages are allowlisted but are
not yet version/snapshot locked, so they are outside this Python-lock baseline
and remain inputs for the later package inventory/SBOM gate.

`assets install` downloads the pinned MuJoCo Menagerie commit, verifies SHA-256, extracts only `franka_emika_panda`, and preserves its license.

## OS launchers

- Windows: `START_HERE.cmd`
- Linux: `start_here.sh`
- macOS: `START_HERE.command`

All three call `scripts/start_mclab.py`.

If a supported Python or platform check fails, install a supported CPython and
recreate the dedicated `.venv`. The launcher can reconcile a trusted profile
promotion or committed lock-input update automatically. It deliberately
preserves and rejects an environment whose recorded inventory, state, or
installed-file integrity has drifted; recreate `.venv` instead of attempting an
in-place repair.

## Updating dependency locks

Dependency updates are reviewable changes, not an implicit install-time
resolution. After editing exact pins in `pyproject.toml` or
`requirements/build.in`, run the generator in its disposable tool environment:

```bash
python scripts/manage_dependency_locks.py --write
python scripts/manage_dependency_locks.py --check
python .agents/validation/check_dependency_locks.py
```

Review the selected versions, upstream changes, licenses, and platform-wheel
coverage before committing all regenerated files together. The generator is
pinned separately, runs in a fresh temporary venv, and is deleted afterward;
it is never installed into the project `.venv` or learner profiles. The build
profile also pins `tomli` so the policy checker works under CPython 3.10.

## Release policy

Build one-folder applications separately on Windows 11 x64, Ubuntu 24.04 x64, and macOS arm64/Intel. Windows signing and macOS notarization are production gates. CI artifacts are explicitly unsigned development builds.

Target compressed release size: 300 MB or less. Target installed cold start p95: 5 seconds or less.
