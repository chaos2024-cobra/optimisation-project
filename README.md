# Satellite Observation Scheduling: rapid replanning for urgent Earth observation

**Team name:** Astra
**Members:** Naksh Sharma, R Krish, Arjun Kesav S
**Course:** Optimization, IIIT Bangalore

## What it does
When an urgent request (e.g. flood mapping) arrives after a satellite plan has been issued, we insert it
while changing as little of the existing plan as possible. The lexicographic objective is
(1) urgent priority, (2) routine priority, (3) fewest changes to the previous plan, (4) least energy.

Four methods are implemented and compared:

| Method | Where |
|---|---|
| Greedy insertion (earliest feasible window, no displacement) and greedy + evict | `solvers.py` |
| Exact search grouped by target (branch and bound) | `solvers.py: dfs_exact` |
| **Restricted replanning** (unlock urgent windows and linked commitments, widen if needed) | `solvers.py: restricted_replan` |
| Full-horizon MILP, lexicographic (HiGHS via SciPy), used as the reference optimum | `solvers.py: milp_lex` |

## Libraries
Python 3.9+, `numpy`, `scipy` (>= 1.9), `matplotlib`. No other solver or licence needed.

## Setup
```
pip install -r requirements.txt
```

## How to run (all from this folder)
```
python check_correctness.py      # ~10 s: brute force == exact search == MILP on 120 small instances, feasibility checks
python run_pilot.py              # static pilot: 2 satellites, 6 targets, 12 windows
python demo.py                   # one alert end to end, writes results/demo_gantt.png
python run_experiments.py --quick        # ~2 min smoke test
python run_experiments.py --seeds 60     # full sweeps used in the report (~10-12 min), writes results/*.csv
python make_figures.py           # figures + LaTeX tables from results/*.csv
```

## Real-orbit case study
`real/` holds a TLE snapshot (5 Earth-observation satellites, 2026-11-23), 8 Indian flood-prone sites and the
Skyfield/SGP4 pass generator `real_windows.py` (see `real/DATASET_README.md`). The 7-day pass list
`real/data/real_windows.csv` is included, so `run_real.py` runs directly:
```
python run_real.py        # ~1 min, writes results/real_sweeps.csv, real_scenarios.csv, table_real.tex
```
To regenerate the passes (needs `skyfield`, `sgp4`):
```
cd real
python prepare_inputs.py  # only if data/tle_snapshot.tle is missing: rebuilds it from data/tle_elements.csv
python real_windows.py --start 2026-11-23T12:38:00Z --days 7 --min-elevation 10 --step-seconds 30
```
`real_data.py` turns passes into scheduling candidates. Its assumptions (pointable sensor with off-nadir limit,
daylight proxy, 5-minute slot, synthetic priorities/energy/budgets) are documented at the top of that file and in the report.

## Files
- `model.py` : data classes, random instance generator, alert builder (freezing, deadline), scoring and feasibility check
- `solvers.py` : all solvers
- `real_data.py`, `run_real.py`, `real/` : real-orbit adapter, experiments, TLE data and pass generator
- `check_correctness.py`, `run_pilot.py`, `demo.py`, `run_experiments.py`, `make_figures.py`
- `results/` : CSVs, figures and the Gantt chart used in the report

All experiments are seeded and reproducible. Timings depend on the machine.
