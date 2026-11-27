# Satellite replanning (basic version)

One script. Needs `scipy` (installs numpy too): `pip install -r requirements.txt`. Python 3.9+.

    python scheduler.py                                  # uses passes.csv
    python scheduler.py passes.csv FLOOD 90 150 12       # file, urgent target, alert time, deadline, energy budget per satellite

## Validation

    python validate.py [passes.csv] [number_of_alerts] [output.csv]

Replays random alerts (fixed seed, default 20), runs all four methods three times each, checks every plan
(candidate passes only, one pass per target, no overlaps, energy budget, frozen passes kept, nothing new
inside the freeze window, urgent pass ends by the deadline), and writes `validation.csv`. Also prints a
summary: deadlines met, how often each method matches the full MILP's result, median runtime.
`python scheduler.py` runs the same checks on its single alert and prints `INVALID:` lines if any fail.

## Dataset (`passes.csv`)

One row per candidate observation. Add or edit rows to try your own data.

    id,satellite,target,start,end,priority,energy

## What it does

1. Builds the issued plan with exact search (one pass per target, no overlaps on a satellite, energy budget per satellite).
2. An urgent target arrives. Passes starting within 5 time units of the alert (`FREEZE`) stay fixed.
3. Compares three ways to add it:
   - Greedy: earliest urgent pass that fits, old plan untouched.
   - Restricted: exact search over the urgent target plus the 3 most related planned targets (time overlap, same satellite, closeness), growing by 3 until the urgent target fits.
   - Full search: exact search over every unfrozen target (reference optimum).
   - Full MILP: the same problem solved as a mixed-integer program (four solves, one per objective), via `scipy.optimize.milp`.
4. Objective order: urgent priority, routine priority, fewer changes, less energy.

Exact search grows quickly with targets, so keep the CSV to roughly 12 targets or fewer.
