# Learner guide

Start on Home and use one primary action: **Start next experiment**. The first Lab01 opens paused at
0.00 s with focus on **Push**: create motion, change **Damping**, select **Play**, then replay the
saved recording. Later hands-on steps add the prediction and observation evidence flow below.

1. Read the goal and write a prediction.
2. Start the scene.
3. Change one highlighted control.
4. Pause or step once to inspect the response.
5. Review the saved priority plot.
6. Replay the recording without recomputing physics.

During a live experiment, the progress strip only shows elapsed progress; it is not a seek control.
Use **Pause** and **Advance 0.1 s** to inspect live physics. Seeking becomes available only after you
open a saved recording.

Playback speed applies to the current app session and carries into a restarted experiment or saved
recording. With the speed selector focused, use the Up/Down arrows to choose 0.25×, 0.5×, 1×, or 2×.

In replay, use the timeline or the first/previous/play/next/last-frame buttons. Rose diamond
markers jump to the exact saved interaction event. Turn on **Loop** to repeat a selected range;
seeking and frame buttons pause on the chosen evidence. **Replay recording** restores saved state,
while **Run again with same settings** performs new physics.

On Results, read the one-sentence outcome, three important values, and recommended next action
before opening **View report**. **Replay recording** is the secondary evidence action. Advanced
reruns, the saved tuning, the output folder, and recoverable cleanup stay under **Manage**. MCLab
never removes saved runs automatically. Cleanup requires you to type the exact folder name, then
moves that run to quarantine instead of permanently deleting it. In a source or virtual
environment, use `python -m mclab clean --list-trash`, then replace `RECEIPT_ID_FROM_LIST` in
`python -m mclab clean --restore RECEIPT_ID_FROM_LIST` with a receipt ID marked `restorable` if you
need to restore it. The list also keeps `history-only` entries for already restored or fully
rolled-back operations. A `busy` receipt cannot be restored until the active cleanup or restore
finishes. The installed GUI bundle currently has neither a cleanup/receipt console nor a
receipt-restore button. Cleanup and restore are supported only on local filesystems; do not run them
on NFS, SMB, or another network filesystem. To recover a run quarantined by the packaged GUI, set
`MCLAB_DATA_DIR` in the source/venv terminal to the same packaged data parent first: `%LOCALAPPDATA%\MCLab`
via PowerShell on Windows, `$HOME/Library/Application Support/MCLab` on macOS, or
`${XDG_DATA_HOME:-$HOME/.local/share}/mclab` on Linux. If the GUI used a custom value, reuse that
exact parent. Then list receipts and restore; otherwise the source checkout searches its own
`outputs/`. Copyable OS-specific commands are in the KR/EN README cleanup section.
Read [Local data and privacy / 로컬 데이터와 개인정보](local_data_and_privacy.md)
before using a shared PC or sharing a run; learner predictions and observation notes also
appear in replay, report, worksheet, and cumulative-index copies.

The default learning path moves from 1D dynamics to PID, 2DOF Jacobian/DLS, Panda Cartesian control, and the virtual wall. Explore contains optional comparisons and advanced variants. Combine its search field with the directly labeled Level and Mode filters; the count updates immediately. Multiple search words all have to match but can appear in any order, so `lab04 wall` and `wall lab04` find the same set. If nothing matches, **Reset filters** clears all three conditions and returns focus to search.

Learning path exposes one recommended **Start next experiment** action instead of asking you to
choose among every future step. Only a successfully completed saved run advances the progress bar;
stopped or failed runs remain the next step. After the 11 hands-on and automatic experiments, the
12th and final step runs all five comparison sets in the background. The app stays usable, shows
progress from 1/5 to 5/5 with the current topic, and offers **Cancel comparison**. Once stopping
begins the button is disabled so the same request cannot be submitted twice. Keep the app open until
completion; the Results page then opens the combined report and learner worksheet. After this comparison succeeds,
the action changes to **Review results** instead of silently rerunning the last experiment.

Current state is cyan/solid/circle, target is violet/dashed/diamond, force is rose/arrow, and wall or constraint is amber/patterned.
