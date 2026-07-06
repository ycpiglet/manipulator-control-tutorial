---
title: 'MuJoCo Manipulator Control Lab: a failure-driven laboratory for learning impedance control safely'
tags:
  - robotics
  - control education
  - impedance control
  - MuJoCo
  - simulation
authors:
  - name: Youncheol Jung
    orcid: 0009-0000-5282-881X
    affiliation: 1
affiliations:
  - name: Independent Researcher, Republic of Korea
    index: 1
date: TODO submission date
bibliography: paper.bib
---

# Summary

Mass-produced collaborative robots and humanoids are reaching users who are
not control engineers, yet the control mode that makes physical interaction
safe — impedance control [@hogan1985impedance] — is exactly the one whose
misconfiguration breaks things: a stiffness set too high with a target set
too far stores enough elastic energy to launch an arm before it ever touches
its goal. *MuJoCo Manipulator Control Lab* (`mclab`) is a local-first,
open-source teaching laboratory built on MuJoCo [@todorov2012mujoco] that
lets learners experience these accidents safely and for free, and then
understand them quantitatively.

The lab sequence walks a beginner up a single coherent ladder: a 1-D
mass-spring-damper plant (stiffness, damping, energy), PID feedback
(gain trade-offs, saturation, windup, delay), a 2-DOF arm (forward/inverse
kinematics, Jacobians, singularities, trajectory profiles), and a 7-DOF
Franka Panda [@menagerie] (joint- and Cartesian-space control, impedance
parameters, virtual-wall contact). Every configuration ships with a
learning guide (focus, what to try, what to watch, suggested next runs),
and every run produces plots and an HTML report, so the material works for
unsupervised self-study. A *failure gallery* reproduces real
misconfiguration accidents — e.g. the stored-elastic-energy launch, where
learners first predict the ~10 m/s peak speed with
$v \approx \delta\sqrt{k/m}$ and then watch the simulator confirm it —
turning expensive hardware trial-and-error into a free, repeatable
experiment.

# Statement of need

Impedance-control literature is written for specialists: derivation steps
are skipped, notation varies between authors, and safe-tuning intuition is
scattered across textbooks [@lynchpark2017]. Learners who will soon operate
physical robots need the opposite: one consistent path from second-order
dynamics to impedance parameters, with every claim checkable by running an
experiment. Existing MuJoCo teaching material focuses on reinforcement
learning or research pipelines rather than classical interaction control
for beginners. `mclab` fills this gap with a tested (340 tests and 760+
subtests in CI, statement coverage above an enforced 80 % floor),
Apache-2.0 codebase whose educational content is CC BY 4.0, and whose test
suite enforces that *every* shipped configuration carries a learning guide
and suggested next runs — the pedagogical scaffolding is itself gated.

A companion long-form tutorial manuscript (Korean, English version in
preparation) develops the full theory with no skipped derivation steps;
its numeric examples are machine-verified against the same formulas the
simulator uses, and its failure cases point back to the exact configs that
reproduce them.

# Learning objectives and experience of use

After the four labs a learner can (1) read overshoot, settling, and energy
exchange from second-order responses; (2) tune PID and impedance parameters
deliberately instead of by trial and error; (3) predict interaction forces
and stored energy before commanding a motion ($f=k\delta$,
$E=\tfrac{1}{2}k\delta^2$); and (4) choose between joint-space and
Cartesian impedance for a given task. The labs have been developed and
exercised by the author against the companion manuscript's worked examples;
classroom-scale evaluation is planned and instrumentation hooks (per-run
reports, progress tracking) are already in place.

# Acknowledgements

The Panda model comes from MuJoCo Menagerie [@menagerie].

# References
