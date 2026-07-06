# How Not to Break a Robot with Impedance Control — Three Accidents You Can Safely Reproduce in Simulation

> Based on the open-source [manipulator-control-tutorial](https://github.com/ycpiglet/manipulator-control-tutorial)
> MuJoCo teaching lab. Every accident below is reproducible with a single
> config file — no hardware, no cost, unlimited retries.

## Why impedance control is dangerous for beginners

As collaborative robots and humanoids leave the lab, people who are not
control engineers are starting to configure how robots interact with the
physical world: "yield this much when pushed", "press with this force".
That language is **impedance control** — and misconfiguring it breaks
things. Even as a robotics engineer, I once damaged objects with an
expensive robot arm because I combined stiffness and target position badly.

On real hardware, each mistake costs money. In simulation, it's free.
The three accidents below are simplified versions of things that actually
happened to me.

---

## Accident 1 — Learning by randomly sweeping parameters

When impedance control feels unfamiliar, the natural urge is to twiddle
stiffness, damping, and mass until something feels right. In simulation
that's a virtue; on expensive hardware it's a gamble with a price tag on
every attempt.

Worse, **changing several parameters at once destroys the learning**.
Stiffness \(k_d\), damping \(d_d\), and mass \(m_d\) are coupled through

$$\zeta = \frac{d_d}{2\sqrt{m_d k_d}}$$

so if you change two at once and the response changes, you can't tell why.

**The vaccine:** set safety limits first, start small, change **one thing
at a time**, and write a one-line prediction before each run. If you're
right, understanding compounds; if you're wrong, you've found a good
question.

The repo ships single-axis contrast pairs for exactly this practice:
`configs/lab01_msd/underdamped.yaml` / `over_damped.yaml` (damping only),
`high_stiffness.yaml` / `low_stiffness.yaml` (stiffness only).

---

## Accident 2 — Commanding without computing the stored spring energy (the robot launches)

I set the target far from the current position, cranked the stiffness up,
and sent the command. The arm shot toward the target.

The reason is the energy already stored in the virtual spring. The moment
you enable stiffness \(k_d\) at a distance \(\delta\) from the target,

$$U = \tfrac{1}{2}k_d\,\delta^2$$

is **already loaded**, and the tip feels up to \(f_{\max} = k_d\,\delta\).
Ignoring losses, energy conservation gives the peak speed —

$$\tfrac{1}{2}mv^2 = \tfrac{1}{2}k_d\delta^2
\;\Rightarrow\;
v_{\text{peak}} \approx \delta\sqrt{\frac{k_d}{m}}$$

— a number **you can estimate before pressing enter**.

Concretely: a 1 kg slider held 0.5 m from its target with 400 N/m
stiffness stores 50 J, starts at 200 N, and should peak near 10 m/s. The
simulator measures **9.8 m/s**, and 4 s later it is still tearing around
at 3.7 m/s. The same 0.5 m commanded with 30 N/m and proper damping stores
**13× less energy** and settles gently at 1.4 m/s.

**The vaccine:** before commanding any large offset, compute
\(\tfrac{1}{2}k_d\delta^2\) and \(k_d\delta\). On real hardware, that
one-line sanity check is worth the price of the equipment.

Reproduce: `configs/lab01_msd/f2_launch_high_energy.yaml` (dangerous) vs
`f2_launch_precheck.yaml` (safe).

---

## Accident 3 — Commanded a displacement, the robot stopped short

In impedance mode I moved the target, and the robot stopped partway,
never reaching it. I assumed a fault. It was the controller **working
exactly as designed**.

In impedance control the target \(x_d\) is not a position command — it's
the **anchor of a virtual spring**. If the path meets contact, the robot
stops at the loaded equilibrium

$$x_{\text{ss}} = x_d + \frac{f_{\text{ext}}}{k_d}$$

The gap between where it stopped and the target isn't an error: it's the
robot **pressing on the environment with gap × stiffness of force**.

The virtual-wall experiment shows this exactly: push the target past a
260 N/m wall and the hand stops 3.3 cm into the wall face while the target
keeps going — and the measured wall force, 8.6 N, equals stiffness ×
penetration to the digit.

**The vaccine:** when an impedance-controlled robot "won't go", first ask
what force it's balancing against, then estimate the contact force as
gap × stiffness.

Reproduce: `configs/lab04_panda/impedance_wall.yaml`.

---

## Closing: break things in simulation, where it's free

All three accidents share one trait: **a single line of arithmetic before
the command would have prevented them.** And that arithmetic instinct
builds far faster by breaking things in a simulator than by reading about
it.

The full theory — the history of impedance from telegraph lines, Laplace
transforms derived from the definition, electrical and mechanical
impedance, Jacobians, and how to choose between impedance/admittance/force
control — is developed **with no skipped derivation steps** in the
companion manuscript, and every number above is machine-verified against
the same formulas the simulator uses:

**https://github.com/ycpiglet/manipulator-control-tutorial**

Break things here first. It's free.

---

*Author: Youncheol Jung, independent researcher.
ORCID: [0009-0000-5282-881X](https://orcid.org/0009-0000-5282-881X)*
*Math blocks need KaTeX/MathJax depending on your renderer.*
