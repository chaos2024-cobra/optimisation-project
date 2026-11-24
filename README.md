# Satellite Observation Scheduling with Urgent Replanning

Naksh Sharma (BA2025023), R Krish (BA2025005), Arjun Kesav S (BA2025023)

Given an issued satellite schedule and a newly arriving imaging request, select
a feasible pass by its deadline and preserve routine observations where possible.

## Start here

- Open `demo.html` in a browser for an offline replay with a satellite timeline,
  method comparison, and a list of schedule edits. All 37 scenarios were
  computed in Python. The page plays back those outputs.
- Open `Project_Report.pdf` for the model, validation protocol, results and limitations.
- Follow the commands below to rerun the solvers.

## Run

Python 3.9+ and SciPy 1.9+. NumPy is installed with SciPy.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python replan.py
python validate.py --demo T400_S3_G1_H1
python validate.py --output validation.csv
python -m unittest -v
python export_demo.py
```

Start the viva with the two-satellite floodplain example from `replan.py`.
Then show the research-dataset example. It prints the alert, deadline,
added and removed observations, and the scores of all three approaches.
Use `python replan.py --deadline 10` to demonstrate an impossible deadline.

## Dataset

Three original IAEOSSP benchmark files are bundled with their MIT license.
Source: Rocha, Chagas, Coelho and Subramanian, *The integrated agile Earth
observation satellite scheduling problem*, Computers & Operations Research
184 (2025), 107212. DOI: https://doi.org/10.1016/j.cor.2025.107212
Repository: https://github.com/yurerocha/IAEOSSP
Snapshot: 4eff110d5d6a151f4a591f9b0e3ddf07f0d216ad

| Instance | Declared targets | Satellites | Horizon | Usable imaging windows |
| --- | ---: | ---: | ---: | ---: |
| T200_S3_G1_H1 | 200 | 3 | 1 day | 184 |
| T200_S3_G1_H2 | 200 | 3 | 2 days | 362 |
| T400_S3_G1_H1 | 400 | 3 | 1 day | 371 |

The parser preserves the source target IDs, satellites, visibility windows,
profits and exposure duration. It places one fixed exposure at each usable
window's midpoint and assigns one energy unit per exposure second. The alert
arrivals, deadlines, 60-second freeze window and per-satellite total energy
budgets are controlled experimental inputs. The adaptation omits slew,
downlink, storage, and recharge. These are simulated benchmark instances and
the results are for the adapted scheduling problem.

## Method

Each pass has a binary decision. Select at most one pass per target, enforce
one imaging activity per satellite at a time, and stay within each satellite's
budget. Completed and imminent commitments remain fixed. Urgent passes must
end by their deadline. In lexicographic order, maximize urgent priority,
maximize routine priority, minimize additions and removals, and minimize total
energy. Moving a pass counts as a removal and an addition.

- Greedy inserts the first feasible urgent pass into the existing plan.
- Restricted replanning ranks scheduled targets on urgent-capable satellites
  by direct overlap and temporal proximity. It first opens 3 linked targets
  and their alternate passes, then grows to 6 and 9 as needed. Exact search
  uses one branch per feasible pass or skips the target. If no searched
  neighborhood can serve the alert, it invokes full MILP and records the fallback.
- Full-horizon MILP optimizes all adjustable opportunities with the same
  constraints and frozen commitments. Four separate solves enforce the
  lexicographic objective.

## Validation protocol and results

Seed 202503 selects 12 alert targets per instance. A routine-only MILP produces
the issued schedule with the alert target withheld. Timing, deadline slack,
and budget tightness vary across the cases. Each solver is timed three times
per case and the median goes into the CSV. The validator checks visibility,
target uniqueness, overlap, budget, freezes, and urgent deadlines on every plan.

| Method | Deadlines met | Full objective matches | MILP fallbacks | Median runtime |
| --- | ---: | ---: | ---: | ---: |
| Greedy | 2/36 | 3/36 | 0 | 0.13 ms |
| Restricted | 35/36 | 32/36 | 1 | 1.25 ms |
| Full MILP | 35/36 | 36/36 | 0 | 36.07 ms |

Restricted replanning served all 35 feasible alerts locally. Its single fallback
confirmed that the remaining alert could not be scheduled. The full solver
retained 20 more routine priority points in four cases. The runtimes are
measurements on this environment and this small benchmark slice. The benchmark uses the original
IAEOSSP instance IDs and a fixed replay seed. Timings may vary on reruns.

`validation.csv` contains 108 solver results. `dataset_demo.txt` captures the
benchmark-based presentation example. The course guidelines require the team
to write its submitted code, so use this prototype to reproduce the model,
design the experiments, and check your team's implementation.
