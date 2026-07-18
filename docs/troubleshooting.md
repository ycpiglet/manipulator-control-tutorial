# Troubleshooting

Run `python -m mclab doctor --json` first. Every error should name a cause, one recommended action, and copyable detail.

## Desktop dependency

```bash
python -m pip install -e '.[app]'
```

## GPU or OpenGL

```bash
python -m mclab app --safe-mode
```

Safe mode keeps navigation, controls, logs, and reports available while disabling GPU scene rendering.

## Panda model

```bash
python -m mclab assets install
```

## Corrupt replay

Legacy metrics and plots remain readable. Run the same scenario again to produce a fresh schema-v1 `replay.npz`.

## macOS legacy viewer

MuJoCo's passive viewer must run through `mjpython`. MCLab selects it automatically for compatibility viewer commands.
