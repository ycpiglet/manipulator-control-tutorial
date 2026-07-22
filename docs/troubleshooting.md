# Troubleshooting

Run `python -m mclab doctor --json` first. Every error should name a cause, one recommended action, and copyable detail.

## Desktop dependency

```bash
python scripts/install_locked.py app
```

The desktop app requires CPython 3.10-3.12 and a reviewed target: Windows 10
version 1809+ or Windows 11 on AMD64, Linux x86-64 with glibc 2.34+, or macOS
13+ on arm64/x86-64. For a headless environment, use
`python scripts/install_locked.py runtime`; its floor is glibc 2.28 on Linux
and macOS 11. Run these commands only after activating the repository's regular
(non-linked) `.venv`.

If the installer reports an invalid state, RECORD mismatch, linked `.venv`, or
an unrecorded non-empty environment, do not try to repair that environment in
place. Remove `.venv`, recreate it with a trusted supported CPython, activate
it, and rerun the locked profile. This is required because Python startup may
process local `.pth` or `sitecustomize.py` files before the installer begins.

## GPU or OpenGL

```bash
python -m mclab app --safe-mode
```

Safe mode keeps navigation, controls, logs, and reports available while disabling GPU scene rendering.

## Panda model

First rerun the setup diagnosis and read the exact missing or invalid path:

```bash
python -m mclab doctor
python -m mclab assets verify
```

If the Panda runtime tree is missing, install the pinned asset set:

```bash
python -m mclab assets install
```

If the tree exists but the doctor, learner menu, application, model loader, or
desktop build reports a size/hash/inventory mismatch, replace the physical tree:

```bash
python -m mclab assets install --force
```

The verifier rejects unknown or missing files, content changes, links, Windows
reparse points, and special files. That includes legacy clone/cache trees with
extra Menagerie documentation, examples, or altered assets. `--force` is only
for an invalid physical directory and intentionally does not overwrite unsafe
linked/reparse trees; inspect and remove those objects yourself. If the failure
comes from an installed desktop bundle, rebuild and reinstall the development
bundle from the same reviewed source commit rather than attempting an in-place
asset repair.

## Corrupt replay

Legacy metrics and plots remain readable. Run the same scenario again to produce a fresh schema-v1 `replay.npz`.

## macOS legacy viewer

MuJoCo's passive viewer must run through `mjpython`. MCLab selects it automatically for compatibility viewer commands.
