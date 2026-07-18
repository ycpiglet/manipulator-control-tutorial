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
reruns, the saved tuning, the output folder, and permanent cleanup stay under **Manage**. MCLab
never deletes saved runs automatically; permanent cleanup shows the folder and warning first.

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
