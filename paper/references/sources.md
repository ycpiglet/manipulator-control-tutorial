# Reference Source Manifest

Initial download check: 2026-06-27.
Coverage audit: 2026-06-30 KST.

This manifest records where each manuscript citation comes from and how local files should be treated.
It is not a license grant.
Only openly reachable PDFs were downloaded, and paywalled or bot-check-blocked PDFs were not bypassed.

## Repository Policy

- Keep `paper/references/refs.bib` and this manifest under version control.
- Treat `paper/references/papers/*.pdf` as a local verification cache, not as source material to publish with the repository.
- Do not commit third-party PDFs unless a venue, license, or rights holder clearly permits redistribution.
- Prefer DOI, arXiv, publisher, institutional repository, author page, or official documentation URLs in `refs.bib`.
- Before submission, recheck weak outreach/history pages and replace them with primary or scholarly sources when possible.

The current `.gitignore` ignores the local PDF cache with:

```gitignore
paper/references/papers/*.pdf
```

## Citation Coverage Summary

- Cited keys in the manuscript: 29.
- Cited keys with BibTeX entries: 29.
- Cited keys missing from BibTeX: 0.
- BibTeX entries not currently cited: 2.
- Local PDFs currently present: 15.

Uncited BibTeX entries are retained for possible advanced related-work expansion:
`howell2022predictivesampling` and `mistry2011operationalspace`.

## Cited Source Coverage

| Cite key | Cited | Local PDF | Source type | Source URL | Status |
|---|---:|---|---|---|---|
| `nvidia_physical_ai_2025` | yes | n/a | Industry blog | https://blogs.nvidia.com/blog/national-robotics-week-2025/ | Metadata/web source only. Useful for current Physical AI framing, but should be framed as industry context. |
| `abudakka2020variableimpedance` | yes | n/a | Open journal article | https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2020.590681/full | Metadata/web source only. DOI in `refs.bib`. Strong source for variable impedance review context. |
| `todorov2012mujoco` | yes | n/a | DOI/publisher metadata | https://doi.org/10.1109/IROS.2012.6386109 | Metadata only. Automated PDF retrieval returned publisher/authentication pages. |
| `tassa2020dmcontrol` | yes | `papers/tassa2020_dm_control.pdf` | arXiv | https://arxiv.org/pdf/2006.12983 | Downloaded from arXiv. |
| `tassa2018deepmindcontrolsuite` | yes | `papers/tassa2018_deepmind_control_suite.pdf` | arXiv | https://arxiv.org/pdf/1801.00690 | Downloaded from arXiv. |
| `zhu2020robosuite` | yes | `papers/zhu2020_robosuite.pdf` | arXiv | https://arxiv.org/pdf/2009.12293 | Downloaded from arXiv. |
| `zakka2025mujocoplayground` | yes | `papers/zakka2025_mujoco_playground.pdf` | arXiv | https://arxiv.org/pdf/2502.08844 | Downloaded from arXiv. |
| `xu2024frankamujocoenvs` | yes | `papers/xu2024_franka_mujoco_envs.pdf` | arXiv and conference metadata | https://arxiv.org/pdf/2312.13788 | Downloaded from arXiv. DOI in `refs.bib`. |
| `ethw_heaviside` | yes | n/a | Institutional history wiki | https://ethw.org/Oliver_Heaviside | Metadata/web source only. Good for accessible historical context; verify details against scholarly sources for formal publication. |
| `heaviside_electrical_papers` | yes | n/a | Public-domain book scan | https://archive.org/details/electricalpapers01heavuoft | Metadata/web source only. Primary historical source. |
| `ptb_impedance_history` | yes | n/a | Metrology/history article | https://www.ptb.de/empir2019/index.php?id=1267 | Metadata/web source only. Supports the Heaviside impedance-term claim. |
| `donaghyspargo2018heaviside` | yes | n/a | Scholarly article | https://doi.org/10.1098/rsta.2018.0229 | Metadata only. DOI in `refs.bib`. |
| `ohm1827galvanischekette` | yes | n/a | Public-domain book scan | https://archive.org/details/bub_gb_tTVQAAAAcAAJ | Metadata/web source only. Primary historical source for Ohm's mathematical treatment of the galvanic circuit. Smithsonian Heralds of Science was also checked as a stable catalog/context source. |
| `faraday1832experimentalresearches` | yes | n/a | DOI/publisher metadata and public-domain scan | https://doi.org/10.1098/rstl.1832.0006 | Metadata/web source only. Primary publication of Faraday's electromagnetic induction experiments; an Internet Archive scan of the Philosophical Transactions volume was also checked. |
| `leyden_jar` | yes | n/a | Museum/educational history page | https://nationalmaglab.org/magnet-academy/history-of-electricity-magnetism/museum/leyden-jars-1745/ | Metadata/web source only. Supports accessible Leyden jar history. |
| `hooke1678depotentiarestitutiva` | yes | n/a | Public-domain book scan | https://archive.org/details/bim_early-english-books-1641-1700_lectures-de-potentia-res_hooke-robert_1678 | Metadata/web source only. Primary historical source for Hooke's spring law and the phrase `ut tensio, sic vis`. |
| `libretexts_viscous_damping` | yes | n/a | Open textbook page | https://eng.libretexts.org/Bookshelves/Mechanical_Engineering/Mechanics_Map_(Moore_et_al.)/15:_Vibrations_with_One_Degree_of_Freedom/15.2:_Viscous_Damped_Free_Vibrations | Metadata/web source only. Suitable for tutorial damping terminology. |
| `newton1687principia` | yes | n/a | Digital library scan | https://cudl.lib.cam.ac.uk/view/PR-ADV-B-00039-00001/1 | Metadata/web source only. Primary historical source for Newton's laws of motion; Library of Congress and Smithsonian records were checked as stable fallbacks. |
| `hogan1985impedancepart1` | yes | `papers/hogan1985_impedance_part1.pdf` | MIT-hosted PDF plus DOI | https://doi.org/10.1115/1.3140702 | Downloaded from MIT-hosted author/course page. DOI in `refs.bib`. Core source. |
| `khatib1987operationalspace` | yes | `papers/khatib1987_operational_space.pdf` | Author/institution-hosted PDF plus DOI | https://khatib.stanford.edu/publications/pdfs/Khatib_1987_RA.pdf | Downloaded from Stanford author page. DOI in `refs.bib`. Core source. |
| `lynchpark2017modernrobotics` | yes | n/a | Official textbook/course resource | https://modernrobotics.northwestern.edu/ | Metadata/web source only. Canonical source for robot joints, configuration/task/work space, forward and inverse kinematics, Jacobians, velocity kinematics/statics, and trajectory generation. |
| `berscheid2021ruckig` | yes | n/a | RSS paper page and project documentation | https://roboticsconference.org/2021/program/papers/015/index.html | Metadata/web source only. Used as a modern reference for jerk-limited online trajectory generation, not as an implemented dependency in the MuJoCo labs. |
| `choi2021simulationrobotics` | yes | n/a | DOI/publisher metadata | https://doi.org/10.1073/pnas.1907856118 | Metadata only. PNAS/PMC/HAL PDF endpoints returned bot-check or non-PDF pages. |
| `collins2021physicsreview` | yes | `papers/collins2021_physics_simulators_review.pdf` | Institutional repository plus DOI | https://ora.ox.ac.uk/objects/uuid:e64b1797-917d-4b75-8eae-a5a60af74246/files/sx346d596k | Downloaded to ignored local cache from Oxford Research Archive. DOI in `refs.bib`. |
| `buss2005sdls` | yes | `papers/buss2005_sdls_ik.pdf` | Author page plus DOI metadata | https://mathweb.ucsd.edu/~sbuss/ResearchWeb/ikmethods/SdlsPaper.pdf | Downloaded to ignored local cache from author page. DOI in `refs.bib`. |
| `schinstock1994robustik` | yes | `papers/schinstock1994_robust_dls_dynamic_weighting.pdf` | NASA Technical Reports Server | https://ntrs.nasa.gov/api/citations/19950005142/downloads/19950005142.pdf | Downloaded from NASA Technical Reports Server. |
| `sartorius2006virtualremote` | yes | `papers/sartorius2006_virtual_remote_lab_manipulator_control.pdf` | Journal PDF | https://www.ijee.ie/articles/Vol22-4/02_ijee1814.pdf | Downloaded to ignored local cache from International Journal of Engineering Education. Supports remote/virtual manipulator-control lab context. |
| `hoenig2016seamless` | yes | `papers/hoenig2016_seamless_robot_simulation_education.pdf` | Author-hosted PDF | https://atavakol.github.io/pub/hoenig2016seamless.pdf | Downloaded to ignored local cache from author-hosted page. Supports robot simulation education framing. |
| `dixon2002matlablab` | yes | `papers/dixon2002_matlab_control_lab.pdf` | University author/lab PDF plus DOI metadata | https://ncr.mae.ufl.edu/papers/te02.pdf | Downloaded to ignored local cache from University of Florida author/lab page. Supports standardized control-lab software and shared resources. |

## Uncited Source Inventory

| Cite key | Local PDF | Source type | Source URL | Status |
|---|---|---|---|---|
| `howell2022predictivesampling` | `papers/howell2022_predictive_sampling_mujoco_mpc.pdf` | arXiv | https://arxiv.org/pdf/2212.00541 | Downloaded from arXiv. Keep for future MuJoCo/MPC context or remove from BibTeX if unused. |
| `mistry2011operationalspace` | `papers/mistry2011_operational_space_constrained_underactuated.pdf` | Proceedings PDF | https://www.roboticsproceedings.org/rss07/p31.pdf | Downloaded from RSS proceedings. Keep for advanced operational-space extension. |

## Local PDF Header Check

All 15 downloaded files under `paper/references/papers/` were checked for a `%PDF` file header after download.

The files remain useful for local reading and verification, but the repository should rely on metadata and URLs rather than redistributing the PDFs.
