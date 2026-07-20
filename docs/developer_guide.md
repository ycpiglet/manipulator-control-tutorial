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

Saved-run cleanup must go through `ArtifactRepository.delete_path` and the shared
`mclab.output_cleanup` boundary. Listing rejects symlinks, junctions, reparse points, special entries,
and malformed saved-run metadata before presenting or sizing a record. The selected lexical path must
be a physical direct child of the configured outputs root; the caller supplies the exact folder name
and the identity token returned when the record was listed. A changed token, active/running record,
preserve marker, root mismatch, or link fails closed.

Bulk CLI cleanup and the Qt single-result action share one strict eligibility rule. The manifest must
use JSON integer `schema_version: 1` (a boolean is not an integer for this contract), contain a
non-empty scenario ID, a `completed`, `stopped`, or `error` status, aware start/finish times, resolved
config mapping, and safe artifact paths. Presentation may still read a legacy `summary.json` so old
results remain visible, but cleanup never falls back to it. Legacy, incomplete, malformed, and
`running` results remain in place with a deterministic rejection reason.

The UI keeps cleanup behind **Manage** and requires the learner to type the folder name. Successful
cleanup uses same-filesystem, non-overwriting renames into `.mclab-trash/<receipt>/entries/`; it never
calls `rmtree`. `mclab clean` is also dry-run by default, applies only an unchanged plan ID plus
`--yes`, and supports receipt listing and restore. A failed multi-entry move or restore attempts a
best-effort rollback; if that rollback also encounters I/O failure, the receipt records the split
state so a later restore can converge without discarding either copy. Quarantine is recoverable but
does not reclaim disk space; permanent purge is intentionally outside SAFE-01.

Each operation first opens the configured root through a lexical, no-link component chain and keeps
that root, the quarantine directory, the receipt, and `entries/` pinned for the transaction. POSIX
uses root-relative descriptors; Windows holds the lexical ancestor handles and the root file ID. A
root-scoped non-blocking operation lock serializes planning, quarantine, and restore across processes;
receipt listing reports otherwise recoverable entries as `busy` while that lock is held. Stable root
identity is deliberately separate from plan freshness, so permission-only changes do not orphan a
receipt while child, metadata, or timestamp changes invalidate an old plan. Receipt reads and writes
share a 2 MiB hard limit, and quarantine and restore preflight the worst-case future receipt before
the first move. Rollback checks the recorded run identity before and after every reverse move.

Every forward quarantine and restore move also carries the source's captured physical identity to
the rename boundary. POSIX keeps a descriptor for that source, checks the destination identity after
the no-replace rename, and attempts a safe reverse move if an unexpected object crossed the boundary.
Windows checks the expected volume/file ID on the same delete-capable source handle used for its
no-replace rename. A post-commit error is recorded as a staged, recoverable state when reversal cannot
be proven safe.

SAFE-01 is designed for local filesystems on the supported desktop platforms. Local Linux evidence
exists for this candidate; APFS and NTFS behavior remains pending until the exact-head macOS and
Windows gates pass. Network filesystems such as NFS/SMB, abrupt power-loss durability beyond the
filesystem's guarantees, and permanent quarantine purge are outside SAFE-01. Do not broaden that
support claim without platform-specific fault and recovery tests.
Windows ReFS-specific file-ID semantics are also not claimed. The operation lock coordinates MCLab
processes; a same-privilege hostile process that ignores it remains outside the cooperative contract,
although identity checks and conservative indeterminate receipts still protect recoverability where
the mutation is observable.
Receipt listing is a read-only snapshot rather than a mutation authorization boundary: restore
reacquires the root lock and revalidates the receipt. A malformed receipt currently stops the list
fail-closed instead of being summarized as an isolated unsafe row; keep that operability limitation
visible until a tested corrupt-receipt representation is added.

Artifact writers must make terminal publication the eligibility boundary. A new run or batch claims a
unique directory; explicit non-empty paths are rejected, and an empty explicit run path is claimed
atomically. Writers publish `running`, then data, plots, learner artifacts, and report, and write the
strict terminal manifest last. Nothing inside that output may be written after terminal publication.
RunLogger report failure stays `running` and retryable, while a finalized logger rejects later writes.
Standalone batch failure writes a hashed `error` manifest after synchronous work has stopped and
re-raises the original error; failure to write `completed` must remain fail-closed, not be rewritten as
another terminal state.

`course_progress_payload` is the single presentation snapshot for Home and Learning path. It counts
only records whose manifest status is `completed`, returns an empty `nextId` at the true end state,
and supplies the localized next scenario and ordered rows together. The synthetic final stable ID
`batch.all` is the 12th step after the 11 scenario runs. Home must route a completed course to
Results; it must never fall back to rerunning the final step. Learning path keeps one primary
next-step button, while completed and upcoming rows are status-only orientation.

The final comparison runs through `QProcess`, never the GUI thread. Desktop launch passes a 256-bit
one-shot handoff token whose SHA-256 is stored in the running manifest. Claiming requires regular
metadata files, rejects link/reparse aliases, and atomically creates an active directory; a second
claim cannot reuse the output. The CLI emits the private
`MCLAB_BATCH_PROGRESS current/total name` protocol before each of five sets. Cancellation first
terminates and then kills after a short grace period; duplicate launch is rejected. The child writes
each standalone child and group completed manifest after its artifact hashes so finalization cannot
freeze Qt. Persisted strict terminal status is authoritative over late cancel or process-error
callbacks. A persisted `running`
manifest with no active process is presented as stopped/retryable after restart. An active output
folder must be protected both by disabled Results management and the backend quarantine guard.

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
moving unrelated saved evidence to quarantine. While an experiment is active, all saved-run cleanup
is blocked. During a comparison batch, only the active batch output is protected at the
repository-facing backend boundary, so unrelated saved evidence can still be quarantined.

Explore filtering stays presentation-only and operates on stable manifest fields. Scenario payloads
expose canonical `difficultyId` plus `requiresEvidence`; QML must not infer level or hands-on mode
from translated card text. Keep Search, Level, and Mode directly labeled, announce the live shown/total
count, and present an explicit reset when zero scenarios match. The keyboard contract is Search →
Level → Mode, while Reset returns focus to Search. Audit all 72, hands-on 9, Build + hands-on 2, and
zero → reset 72 states in both languages and at 640×360. Search semantics are token-AND, not one
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
