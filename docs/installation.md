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
warning-free controlled repository output, and a verified evidence file.
It uses a temporary official-Ubuntu-only Deb822 source file plus isolated APT
configuration, source parts, preferences, authentication, trust, package-list,
cache, and archive state. Host hooks and proxy variables are excluded, APT and
dpkg use absolute system paths, and TLS peer/host, repository-strength, and
metadata-date checks are explicitly enabled. Hosted-runner Microsoft, Docker,
mirror, preference, hook, or cached-index configuration therefore cannot enter
candidate selection. Conflicting or disabling
per-repository snapshot settings, snapshot-ID mismatch, unapproved repository
identities, insecure or unauthenticated fallback, timeouts, and version or
architecture drift fail closed. The Ubuntu archive keyring is pinned to the
official Noble `ubuntu-keyring==2023.11.28.1` payload (3,607 bytes, SHA-256
`80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31`). The
installer opens the source without following symlinks, verifies the exact bytes,
and gives APT only a new `0644` copy inside its isolated temporary state. A loose
host-image mode such as `0777` is therefore not treated as trust. The keyring pin
is a closed field in the Ubuntu manifest and generated SBOM-input contract, and
the installation evidence records the observed verified size and digest rather
than the temporary copy path. This relies on the Ubuntu image's root-owned
`/usr/share/keyrings` parent and excludes a concurrent hostile root process. This
controls the direct package set and repository point in time; it is not a frozen
base image or a complete native transitive-library inventory.

APT's update status reports the configured logical Ubuntu archive URLs even
when the Deb822 `Snapshot` field selects the timestamped backend. The installer
therefore accepts status URLs only from those two exact HTTPS Ubuntu endpoints
or the exact timestamped snapshot endpoint. Before any fetch, it runs APT's
`--print-uris` planner against the same isolated state and validates the planned
timestamped physical `InRelease` route for all four controlled suites, exact
physical/logical target parity, and strict record syntax. It also requires the
preflight to leave no detected metadata or content change in the isolated
state. The explicit Deb822 `Snapshot` value is the binding selection; `-S` and
`APT::Snapshot` are two spellings of the same redundant command-level guard.
The subsequent real update validates reachability, system-CA TLS, Ubuntu-keyring
signatures, candidates, and versions; the preflight is not network attestation.

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
Hosted-interpreter bootstrap packages outside the reviewed package profile are
explicitly excluded from this bounded scanner profile. That exclusion does not
prove they are absent from a future shipped package; distribution closure
remains pending. The target probe requires every lock-derived package at its
exact version, and `pip-licenses --packages` limits this evidence to that same
deterministic set. Ambient packages therefore neither enter this evidence nor
relax missing-package, version, or scanner-output coverage checks.

LIC-01A adds a committed, closed-schema inventory contract without adding
third-party license or NOTICE bodies. The registry fixes all 49 package-lock
candidates and their membership across the reviewed 12 CPython/platform cells,
then records bounded summaries and SHA-256 provenance for the three accepted
SUP-01 hosted observations. The hosted observations are short-lived development
evidence, not release provenance. For package-evidence comparison, the checker
explicitly excludes the bootstrap `pip`, `setuptools`, and `wheel` distributions
and substitutes the editable MCLab project for the package lock's `setuptools`
candidate, matching the existing scanner boundary.

Each accepted target also pins normalized, per-package observations: the raw
license string reported by package metadata, the reported project URL, and
SHA-256 hashes of normalized license and NOTICE text when present. These values
are evidence observations only. They are not reviewed SPDX expressions, legal
interpretations, or approval of the reported terms.

Each target also records the raw artifact SHA-256 and the canonical evidence
SHA-256. Canonicalization version 1 strictly parses UTF-8 JSON, rejects duplicate
keys and non-finite numbers, sorts object keys, renders with two-space
indentation and unescaped Unicode, and terminates lines with LF plus one final
LF. The accepted Windows artifact retains its historical CRLF raw hash while
also recording the hash of the canonical LF form. Newly generated evidence must
be canonical; the checker permits noncanonical bytes only when both hashes match
that exact historical accepted artifact.

The machine-readable coverage record makes the remaining boundary explicit.
Only 3 of 12 target cells have accepted observations; the other 9 are listed by
ID. Across those cells, 48 of 49 locked candidates are applicable, but only 47
locked candidates appear in evidence: `setuptools==83.0.0` is explicitly
excluded on each observed target. The editable
`mujoco-manipulator-control-lab==0.1.0` row is added on each target, producing 48
distinct observation rows. `exceptiongroup==1.3.1` is the sole lock candidate
whose marker is not applicable to any observed target. These absences and the
target-scoped exclusion/addition reasons are machine-readable. Distribution
closure remains `unproven`. The registry nevertheless enumerates the existing
universal SBOM-input surfaces without claiming license review: 22 pinned direct
Ubuntu packages, 72 Panda runtime files, 2 bundled font files, and all 6
packaging data groups.

The registry hashes every direct producer input, including all eight locks read
by the scanner (`uv-tool`, `build`, `runtime`, `app`, `dev`, `app-dev`,
`package`, and `supply-chain-tool`), schemas and checker/generator sources,
project metadata and license, Ubuntu manifest and installer, Panda manifest,
packaging specification, and each bundled font/license file. A test derives
the expected lock set from the scanner itself. Missing or changed producer
inputs fail regeneration before the committed registry can pass.

```bash
python scripts/generate_license_inventory.py --check
python .agents/validation/check_license_inventory.py
```

Every desktop matrix cell validates its fresh `python-licenses.json` against
that registry before evidence upload. Candidate review status nevertheless
remains `pending`, and the contract keeps license-expression, copyright,
license-text, NOTICE, source/relinking, native/base-image, and Qt/PySide LGPL
decisions plus unproven distribution closure as explicit blockers. This
contract is not legal approval, a complete notice bundle, public-distribution
authorization, or permission to reinterpret the existing unsigned development
artifacts as release evidence.

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
