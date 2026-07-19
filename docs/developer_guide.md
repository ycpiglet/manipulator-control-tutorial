# Desktop architecture

The desktop package is under `src/mclab/application/` and has no Qt imports at package import time.

- `ScenarioCatalog`: stable IDs and scenario metadata
- `SimulationSession`: state, stepping, transport, recording, replay, cleanup
- `LabAdapter`: small physics boundary
- `lab03_adapter.py` / `lab04_adapter.py`: integrated 2DOF, DLS, Panda, and wall adapters
- `ArtifactRepository` / `ProgressRepository`: saved run and preference access
- `RunManager`: duplicate launch protection
- `PlatformServices`: OS open/viewer behavior, including macOS `mjpython`
- `qt_batch.py`: nonblocking course-comparison process and Qt presentation boundary
- `qt_app.py` and `qml/`: Qt Quick presentation

Existing CLI labs remain authoritative for controller and trajectory equations. Lab01 through Lab04 now run through the common integrated session; the adapters reuse the existing trajectory, Jacobian, DLS, PID, and virtual-wall functions. `run --viewer` remains a compatibility path, while every saved `replay.npz` opens in the integrated replay renderer.

Replay pacing comes from adjacent recorded timestamps rather than the model timestep. Timeline and
frame seeks pause deterministically, event markers use normalized elapsed time, and Lab04 recordings
must include target X/Y/Z, wall X, wall force, and penetration so the replay renderer can reproduce
the same current/target/force/wall semantics without stepping physics.

`result_payloads` is the presentation boundary for saved runs. It localizes scenario titles through
`ScenarioCatalog`, converts each lab's summary into three semantic metrics, and supplies one outcome
and one recommended next action. The Results QML keeps one shared management dialog instead of a
dialog per delegate, creates only 20 cards initially, and reveals the remaining records in blocks of
20. Do not silently truncate repository records.

Saved-run deletion must go through `ArtifactRepository.delete_path`. The selected path must resolve
to a direct child of the configured outputs root, and the caller must repeat the exact resolved path
as confirmation. The UI must keep cleanup behind **Manage**, show the permanent warning, refresh the
collection immediately, and never perform automatic deletion.

`course_progress_payload` is the single presentation snapshot for Home and Learning path. It counts
only records whose manifest status is `completed`, returns an empty `nextId` at the true end state,
and supplies the localized next scenario and ordered rows together. The synthetic final stable ID
`batch.all` is the 12th step after the 11 scenario runs. Home must route a completed course to
Results; it must never fall back to rerunning the final step. Learning path keeps one primary
next-step button, while completed and upcoming rows are status-only orientation.

The final comparison runs through `QProcess`, never the GUI thread. The CLI emits the private
`MCLAB_BATCH_PROGRESS current/total name` protocol before each of five sets. Cancellation first
terminates and then kills after a short grace period; duplicate launch is rejected. The child writes
the completed manifest and artifact hashes so finalization cannot freeze Qt. A persisted `running`
manifest with no active process is presented as stopped/retryable after restart. An active output
folder must be protected both by disabled Results management and the backend deletion guard.

Every learner-facing QML translation call uses `localizedText(backend.language, key)`. The explicit
language argument is intentional: it gives the binding a Qt notify dependency, so static navigation,
dialog, and transport labels re-evaluate together with model-backed cards during a runtime switch.
Language-switch audits must require the new navigation labels and forbid the previous language.

Runtime errors keep two separate values: `errorMessage` is a short learner-facing cause, while
`errorDetail` retains the raw exception only for the collapsed technical area and copy action. Do
not interpolate exception classes, internal action names, paths, or trace text back into the primary
dialog message. The 200% audit uses a 640×360 logical window with `QT_SCALE_FACTOR=2`; test window
dimensions are injected before QML loads so the window manager cannot maximize the initial 1280×720
default and invalidate the physical 1280×720 capture.

Qt accessibility snapshots include each control's live rectangle. The desktop audit rejects visible
Button, ComboBox, and text-input targets below 44×44 logical pixels; Slider, CheckBox, and timeline
event targets must be at least 24×24. Keep compact hit areas large without shrinking the experiment
viewport. Replay marker presentation must filter camera-only orbit/pan/zoom/reset events and merge
consecutive same-control events within 0.2 seconds into one gesture marker. The replay archive keeps
every raw event; only the timeline presentation is reduced.

Keyboard audits record the live Qt accessible focus object after every tested key. Each step must be
an interactive role with a non-empty localized name and a rectangle fully inside the active window.
Scrollable experiment controls must reveal themselves when focused; use the shared panel helper for
buttons, sliders, and checkboxes instead of allowing an off-screen active focus. Entering an
experiment moves focus to the primary play/pause transport control. Modal dialogs start on the safe
Close action, keep Tab/Shift+Tab inside the modal, and return focus to the invoking control on Escape
or Close. Add an exact `expected_focus_names` sequence whenever a new critical keyboard path is added.

The always-visible live timeline is a read-only `ProgressBar` named Experiment progress. It must not
accept focus or promise seeking. Only a loaded recording exposes the focusable Replay timeline
`Slider`; arrow-key seeking must update the saved frame without recalculating physics. Preserve this
role, name, description, and focus distinction when changing transport layout.

Hands-on sessions start prepared and paused at exactly 0.00 seconds. Saving the prediction records
the evidence and resumes physics in one simulation-thread command. A live restart must clear the
evidence and return to the same paused zero-time state. Replay mode is explicit backend state and
must never inherit the live scenario's prediction gate.

Navigation away from Experiment must queue a pause before changing the page whenever the persistent
worker still owns a live or replay session. `ActiveSessionBar` is present on all four non-experiment
pages and provides only Return plus End and save (Close replay in replay mode). The bar remains until
finalization is idle, and a comparison batch cannot start while that worker is active. Page changes
move keyboard focus to the destination navigation control so an input hidden with the experiment
cannot retain focus. Shared buttons must activate consistently with both Enter and Space.

Home keeps a strict first-viewport priority at 640×360. When setup is ready and no work is active,
the three-step tour precedes the single next-experiment card; the green environment card follows it.
When setup is not ready, `EnvironmentStatusCard` precedes the disabled next action and the tour stays
hidden. An active experiment or comparison also hides the tour so recovery/cancel remains dominant.
Skipping must move focus to the next action, and reopening must move focus back to the tour's Skip
button. Keep these transitions in the accessibility audit instead of relying on fixed timer delays.

The first `lab01.default` manifest uses `application.start_paused` and
`application.core_controls: [damping]`. These keys are desktop presentation metadata: the integrated
app opens at zero time, focuses Push, and progressively discloses one slider, while the established
CLI/headless runner continues the full configured simulation without waiting. Validate the literal
Start → Push → Damping → Play → Replay route with both the saved interaction event names and the
recorded replay, rather than crediting an automatic demo as hands-on course evidence.

Every launch affordance binds to both exclusive-work states: `hasActiveExperiment` and the running
course-comparison batch. Home and Learning path keep their cancel action, while Explore starts,
Results playback, and saved-run reruns are disabled. `reject_running_experiment` and
`reject_running_batch` repeat the same boundary for direct backend calls. A persistent worker thread
is not itself an active experiment: the experiment guard must use `busy` ownership, otherwise one
completed run would block the final course comparison forever. `BatchSessionBar` keeps progress and
cancel visible on Explore and Results. `ResultManageDialog.qml` displays the applicable blocking
reason inside the modal; report/folder/close remain available, and a running batch does not prevent
deleting unrelated saved evidence. Only the active batch output and evidence owned by an active
experiment are protected at the repository-facing backend boundary.

Explore filtering stays presentation-only and operates on stable manifest fields. Scenario payloads
expose canonical `difficultyId` plus `requiresEvidence`; QML must not infer level or hands-on mode
from translated card text. Keep Search, Level, and Mode directly labeled, announce the live shown/total
count, and present an explicit reset when zero scenarios match. The keyboard contract is Search →
Level → Mode, while Reset returns focus to Search. Audit all 70, hands-on 9, Build + hands-on 2, and
zero → reset 70 states in both languages and at 640×360. Search semantics are token-AND, not one
literal substring: trim and split whitespace, require every token in any order, and verify
`lab04 wall` → 14 at both 100% and 200% scale. Keep the scenario list cached once in QML so result
counting does not repeatedly serialize all Python payloads.

Playback speed is backend-owned state, not local ComboBox state. A learner selection must update the
visible value, accessibility description, and `SimulationSession.speed` together, and the selected
speed must carry into a newly created live or replay session. The speed audit records all three
values across completion and replacement. Keep Up/Down keyboard instructions in the localized
description and never leave the selector showing a speed different from physics pacing.

Generated HTML must pass `scripts/audit_report_ui.py` for run, batch, course, and outputs-index
documents at 1280×720 and 390×844. The audit launches stable Chrome through Playwright, runs axe-core
WCAG 2.2 A/AA and best-practice rules, samples Tab focus, and rejects horizontal document overflow,
broken images, heading skips, raw run IDs, expanded advanced details, or inaccessible scroll tables.
Keep wide tables inside a labeled, focusable `.table-wrap`; raw artifact links must remain at least
24px high. The Linux desktop CI runs the same audit on a fresh Lab01 report and outputs index.

New production Python modules must stay at or below 800 lines and QML components at or below 400 lines. Keep UI assembly functions small and move behavior into services.
