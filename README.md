# Satellite Observation Scheduling: Urgent Replanning

**Team Astra** · Optimization Course Project · IIIT Bangalore

## Team

| Name | Roll number |
|---|---|
| Naksh Sharma | BA2025023 |
| R Krish | BA2025035 |
| Arjun Kesav S | BA2025005 |

## Project title

Satellite Observation Scheduling: Urgent Replanning

## Short description

An urgent imaging request (say, a flood) can arrive after a constellation has already committed to a routine schedule. This project compares four ways of fitting that request in (greedy insertion, restricted exact replanning, full exact search, and a full MILP) and shows that an exact search over a small neighborhood of the schedule serves nearly every feasible alert, far faster than re-solving everything.

Full write-up: [Astra_Project_Report.pdf](Astra_Project_Report.pdf)

## Libraries used

| Library | Used for |
|---|---|
| **SciPy** (`scipy.optimize.milp`, `Bounds`, `LinearConstraint`; HiGHS solver) | Full-horizon MILP method |
| **NumPy** (installed with SciPy) | Building the MILP constraint matrices |
| Python standard library (`csv`, `sys`, `time`, `random`, `statistics`) | Data loading, command-line arguments, timing, seeded random alerts, summary statistics |

## Setup instructions

Requires **Python 3.9+**.

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd <your-repo-folder>

# 2. (Optional) create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies (SciPy also installs NumPy)
pip install -r requirements.txt
```

## Running the project

```bash
python scheduler.py                                  # default alert on passes.csv
python scheduler.py passes.csv FLOOD 90 150 12       # file, urgent target, alert time, deadline, energy budget per satellite
python scheduler.py passes.csv FLOOD 90 105 12       # infeasible deadline: every method misses

python validate.py                                   # replay 20 random alerts, write validation.csv
python validate.py passes.csv 50 my_results.csv      # file, number of alerts, output file
```

Example output of the default run:

```
Issued plan: 7 observations, routine priority 44
Alert at 90: FLOOD must finish by 150

Greedy      urgent MISSED routine  44  changes 0  energy 22
Restricted  urgent met    routine  39  changes 4  energy 22  (unlocked 3 of 3 planned targets)
    removed T3 on A 100-110
    removed T8 on B 170-180
    added   FLOOD on A 100-110
    added   T3 on B 120-130
Full search urgent met    routine  39  changes 4  energy 22
Full MILP   urgent met    routine  39  changes 4  energy 22
```

Runtimes are also printed and vary by machine; everything else is deterministic.

## The problem

Each candidate pass is a fixed observation of one target by one satellite, with a priority and an energy cost. A plan picks passes so that:

- each target is imaged at most once,
- passes on the same satellite do not overlap in time,
- each satellite stays within its energy budget,
- passes that start within 5 time units of the alert (the freeze window) stay exactly as issued, and nothing new may start inside it,
- the urgent target's pass ends by the deadline.

Plans are compared lexicographically: (1) urgent priority, (2) routine priority, (3) fewer edits to the issued plan, (4) less energy. A reassignment counts as two edits (one removal, one addition).

## The four methods

| Method | Idea |
|---|---|
| **Greedy** | Insert the earliest urgent pass that fits. The issued plan is never changed. |
| **Restricted** | Open the urgent target plus the 3 most related planned targets (time overlap, same satellite, closeness) and search them exactly. If the urgent target still does not fit, open 3 more, until it fits or every planned target is open. |
| **Full search** | The same exact search with every non-frozen target open. The reference optimum. |
| **Full MILP** | The same problem as a mixed-integer program, via `scipy.optimize.milp` (HiGHS). Four solves, one per objective level, each locking in the previous result. |

## Results

`validate.py` replays 20 seeded alerts (random urgent target, alert time, deadline and energy budget of 10, 12 or 14) and validates every plan from every method. Numbers from the shipped `validation.csv`:

| Method | Deadlines met | Matches MILP | Median time |
|---|---|---|---|
| Greedy | 0/20 | 2/20 | 0.002 ms |
| Restricted | 18/20 | 15/20 | 0.10 ms |
| Full search | 18/20 | 20/20 | 1.01 ms |
| Full MILP | 18/20 | 20/20 | 14.50 ms |

- Two alerts are infeasible for every method (a frozen pass blocks the only urgent pass, or frozen passes have already used too much energy). So 18 of 20 are feasible, and restricted replanning served all 18; greedy served none.
- Restricted replanning is about 145x faster than the MILP and 10x faster than full search at the median.
- In the 5 cases where restricted does not match the MILP, it keeps 10 fewer routine points in total, because it stops at the first neighborhood that works.
- All 80 plans (20 cases x 4 methods) pass the independent checker.

"Matches MILP" means equal urgent priority, routine priority, edit count and energy.

## Files

| File | Purpose |
|---|---|
| `scheduler.py` | Model, the four methods, objective score, plan checker, and the single-alert demo |
| `validate.py` | Seeded replay of random alerts, plan validation, summary table, writes `validation.csv` |
| `passes.csv` | Demo dataset: 15 candidate passes, 2 satellites, 8 routine targets plus the urgent target `FLOOD` |
| `validation.csv` | Per-case, per-method results from the 20-alert replay |
| `requirements.txt` | `scipy>=1.9` |
| `Astra_Project_Report.pdf` | Project report |

## Dataset format

One row per candidate observation in `passes.csv`. Edit or add rows to try your own scenarios.

```
id,satellite,target,start,end,priority,energy
```

Times and energy are in abstract units. A target with several rows has alternate passes. Keep the file to roughly 12 targets or fewer, since the exact-search methods grow exponentially with the number of open targets.

## Validation checks

Every plan returned by every method is checked for: candidate passes only, one pass per target, no overlaps on a satellite, energy budget, frozen passes kept, nothing new inside the freeze window, and the urgent pass ending by the deadline. `scheduler.py` prints `INVALID:` lines if any check fails on its single alert; `validate.py` reports how many plans were valid.

## Limitations

- Tiny hand-written dataset; the replayed alerts are related and do not show mission-scale reliability.
- Urgent requests, energy budgets and the freeze window are simulated.
- Pass times are fixed. Slewing, downlink, storage and attitude constraints are not modeled.
- Restricted replanning stops at the first neighborhood that serves the alert and has no MILP fallback, so it can leave routine value on the table.irst neighborhood that serves the alert and has no MILP fallback, so it can leave routine value on the table.
