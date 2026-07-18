# MCLab

[한국어 README](README.md)

MCLab is a local MuJoCo robot-control learning app. It carries one predict–manipulate–review workflow from a 1D mass–spring–damper plant through PID, 2DOF Jacobian/DLS, and the Franka Panda virtual wall.

![MCLab English home](docs/assets/mclab-home-en.png)

## Start in three steps

1. Select **Start next experiment**.
2. Select **Push**, change **Damping**, then select **Play**.
3. Select **Replay recording**, then explain the priority plot.

| OS | Source launcher |
|---|---|
| Windows 11 x64 | Double-click `START_HERE.cmd` |
| Ubuntu 24.04 x64 | `./start_here.sh` |
| macOS arm64/Intel | `./START_HERE.command` |

The first launch prepares a virtual environment and the licensed Panda assets.

## Manual installation

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -e '.[app]'
python -m mclab assets install
python -m mclab doctor
python -m mclab app
```

MCLab runs one desktop process per user. Launching it again restores and raises the existing window instead of creating a second GPU process.

Headless use does not require Qt:

```bash
python -m pip install -e .
python -m mclab run lab01 \
  --config configs/lab01_msd/default.yaml \
  --headless --plot --plots essential
```

## App

The four top-level destinations are Home, Learning path, Explore, and Results. Explore combines text search with directly labeled Level and Mode filters, a live result count, and a keyboard-reachable reset when no experiment matches. Multi-word searches such as `lab04 wall` match every word in any order. The experiment screen keeps the goal stages, MuJoCo scene, at most five core controls, and Pause/Step/Reset/speed/timeline visible. Physics waits for the learner's prediction and then starts at 0.00 s, so thinking time cannot change the result.

On first launch, Home keeps **Start → Change → Replay** and **Start next experiment** together in the first 640×360 viewport. Skipping moves keyboard focus to the primary action, and **Show tour again** beside the Home title restores the guide. If setup is not ready, its cause and recovery action take priority over the tour.

The first Lab01 opens paused at 0.00 s with keyboard focus on **Push**. Its default panel shows only Pull/Push and one highlighted **Damping** control, so the tour can be completed literally. This app-only prepared state does not pause the same YAML when it runs through CLI/headless physics.

If the run ends before its evidence is complete, **Restart** becomes the only primary action. Enter restarts at 0.00 s and returns focus to prediction; **View saved results** becomes primary only after prediction, one control, and observation are saved.

Prediction examples match each experiment and put the observable first—Damping, P gain, tracking error, singularity, hand or joint target, or contact force—so the key quantity remains visible at 200% zoom.

Lab01/02 directly label the spring, damper, mass block, and equilibrium, alongside a bright floor, scale ticks, current circle, and target diamond. GPU safe mode keeps the same responsive teaching diagram instead of falling back to an empty scene.

Lab03/04 safe mode also remains instructional: it draws a 1D tracking rail, numbered 2DOF arm and workspace, simplified Panda arm, and virtual-wall grid with the same current/target semantics.

Leaving the experiment automatically pauses physics and recording. A persistent session bar on Home, Learning path, Explore, and Results lets the learner return to the experiment or end and save it explicitly.
While that bar is visible, starting, replaying, rerunning, and deleting are disabled; reports and folders remain available for safe review.

Learning path presents one recommended next action and advances only after a successful saved run. When the app path is complete, its primary action changes to **Review results** instead of rerunning the final experiment.

The last of 12 recommended steps runs all five comparison sets in a separate process. The app stays
usable, and a comparison bar on Explore and Results shows the current topic with 1/5–5/5 progress
and cancellation. Until it finishes, new experiments, recording playback, and reruns are disabled;
existing reports, folders, and cleanup of unrelated saved runs remain available. The combined report
and worksheet then appear in Results.

The semantic visual system is consistent: current is cyan/solid/circle, target is violet/dashed/diamond, force is rose/arrow, and a wall or constraint is amber/patterned.

Prediction examples follow the active physics context: damping, P gain, tracking, singularity, joint or hand targets, and virtual-wall contact force each receive a short Korean/English hypothesis instead of reusing the Lab01 oscillation example.

Keyboard users can complete the core flow with Tab, Shift+Tab, Enter, Space, and arrow keys. Space pauses an experiment and Right Arrow steps once.

## Commands

```text
mclab app [--lang ko|en] [--scenario ID] [--safe-mode]
mclab replay <run-dir>
mclab doctor [--json]
mclab assets install
mclab run ...
mclab batch ...
mclab coverage
mclab review
mclab index --open
```

`mclab menu` aliases the new app. The existing `run --viewer` route remains available for compatibility; macOS viewer commands select `mjpython` automatically.

## Reproducible evidence

Every new CLI run automatically saves:

- resolved YAML, 100 Hz CSV, and compressed numeric states;
- a default 60 fps qpos/qvel/ctrl/semantic replay;
- schema-v1 provenance with scenario, status, seed, runtime, model/license, and artifact hashes;
- plots, a result-first HTML report, and worksheet;
- learner events, final snapshot, and tuned YAML when applicable.

Replay recording uses saved states without recomputing physics. Run again with same settings performs a new calculation. Run last tuning uses `learner_tuned_config.yaml` for a new calculation.

Results presents a one-sentence outcome, three important values, and the recommended next action before the primary **View report** action. Advanced reruns, tuned settings, folder access, and permanent deletion stay under **Manage**. MCLab never deletes saved runs automatically; cleanup shows the size and exact folder first.

Legacy outputs stay readable. Recording replay is disabled with a reason when the old run lacks complete MuJoCo state.

## Development

```bash
python -m pip install -e '.[app,dev]'
python -m pytest -q
python -m ruff check src tests scripts
QT_QPA_PLATFORM=offscreen python -m mclab app --self-test
# after installing dev extras: python scripts/audit_report_ui.py --help
```

See [installation](docs/installation.md), [learner guide](docs/learner_guide.md), [educator guide](docs/educator_guide.md), [architecture](docs/developer_guide.md), and [troubleshooting](docs/troubleshooting.md).

## License

Project code is Apache-2.0. The MuJoCo Menagerie Panda model keeps its original license. Asset installation verifies the pinned archive SHA-256 before extracting the Panda folder and license.
