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

The Linux desktop workflow installs its 22 direct Qt/XCB system packages from
the committed Ubuntu 24.04 AMD64 manifest at
`requirements/system/ubuntu-24.04-amd64.json`. The installer requires the
`20260723T000000Z` Ubuntu snapshot, exact candidate and installed versions,
warning-free snapshot-only repository output, and a verified evidence file.
It uses a temporary official-Ubuntu-only Deb822 source file plus isolated
package-list and archive state, so hosted-runner Microsoft, Docker, mirror, or
cached indexes cannot enter candidate selection. Conflicting or disabling
per-repository snapshot settings, snapshot-ID mismatch, mixed/live repository
URLs, insecure or unauthenticated fallback, timeouts, and version or
architecture drift fail closed. This controls the direct package set and
repository point in time; it is not a frozen base image or a complete native
transitive-library inventory.

`assets install` downloads the pinned MuJoCo Menagerie commit, verifies the
archive SHA-256, extracts only the tracked `franka_emika_panda` runtime files,
and preserves the upstream license. The installed tree is then checked against
an embedded, version-controlled file inventory (path, size, and SHA-256 for
every runtime file). Unknown, missing, modified, linked, reparse-point, and
special-file entries fail closed.

`python -m mclab doctor`, learner readiness screens, and every direct Panda
model load enforce that installed-tree contract. Desktop packaging performs the
same verification before PyInstaller starts and bundles only the verified
runtime directory. A frozen application verifies the bundled copy below its
PyInstaller runtime root (`_MEIPASS`) before MuJoCo loads it.

Verify an existing installation without downloading or changing it:

```bash
python -m mclab assets verify
```

Strict verification also rejects legacy full-clone or cache-derived Panda
directories when they contain extra documentation/examples or altered runtime
files. Reinstall the canonical runtime subset instead of treating those extra
files as harmless packaging input.

If the Panda tree is absent, install it normally:

```bash
python -m mclab assets install
```

If a physical Panda tree exists but fails its inventory check, replace it only
after reviewing the reported path:

```bash
python -m mclab assets install --force
```

Links, reparse points, and other unsafe filesystem objects are not replaced by
`--force`; remove or investigate them explicitly. For a damaged packaged
application, rebuild and reinstall the development bundle from the same
reviewed source commit instead of modifying the bundle in place.

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
resolution. After editing exact pins in `pyproject.toml`,
`requirements/build.in`, or a reviewed file below `requirements/tools/`, run
the generator in its disposable tool environment:

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

## Supply-chain evidence

CI installs `pip-audit==2.10.1` and `pip-licenses==5.5.5` only in a disposable
environment from the separate hash-locked scanner profile; the vulnerability
service cache is disposable with it. The universal
vulnerability input removes environment markers only after proving complete
coverage of every package/version pair in all eight reviewed lock profiles
across the 12 target environments. Any scanner failure, malformed response,
uncovered dependency, vulnerability finding, or nonempty waiver registry fails
the gate. Scanner output is normalized before evidence is written so aliases
and service ordering cannot change the committed contract.

The desktop matrix also records a deterministic package-profile license input
for each supported OS family. Missing or unknown license identifiers, license
texts, package URLs, and NOTICE files remain explicit null values and are
counted in `metadata_gaps`; package names, versions, and exact lock coverage
still fail closed on any mismatch. `inventory-complete` means the reviewed
package set was fully recorded, while `compliance_status` remains
`pending-lic-01`. LIC-01 must resolve those gaps before its UNKNOWN=0 release
gate can pass. These records are not legal advice, a complete notice bundle,
or approval to distribute Qt/PySide or any other component.

`scripts/generate_sbom_inputs.py` combines the reviewed Python locks, Ubuntu
direct-package manifest, pinned Panda runtime inventory, bundled fonts, and
immutable GitHub Action references into deterministic SBOM inputs. Generation
requires the supplied source commit to equal a clean checked-out Git `HEAD`.
This is not an OS-specific final SBOM, build provenance, signature, or release artifact.
Native transitive libraries, the trusted CPython/base image, and binary
internals remain outside the Python vulnerability scanner and must be closed
by the later LIC/PKG/REL gates before public distribution.

## Release policy

Build one-folder applications separately on Windows 11 x64, Ubuntu 24.04 x64, and macOS arm64/Intel. Windows signing and macOS notarization are production gates. CI artifacts are explicitly unsigned development builds.

Target compressed release size: 300 MB or less. Target installed cold start p95: 5 seconds or less.
