"""Urgent-request replanning for satellite observations. Needs numpy and scipy (for the MILP).

Usage: python scheduler.py [passes.csv] [urgent_target] [alert_time] [deadline] [budget]
"""
import csv
import sys
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

FREEZE = 5  # passes starting within this many time units of the alert stay fixed


def load(path):
    """Read candidate passes: id,satellite,target,start,end,priority,energy."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("start", "end", "priority", "energy"):
            r[k] = int(r[k])
    return rows


def group(passes):
    """Candidate passes per target."""
    options = {}
    for p in passes:
        options.setdefault(p["target"], []).append(p)
    return options


def clash(a, b):
    return a["satellite"] == b["satellite"] and a["start"] < b["end"] and b["start"] < a["end"]


def fits(plan, p, budget):
    used = sum(q["energy"] for q in plan if q["satellite"] == p["satellite"])
    return used + p["energy"] <= budget and not any(clash(p, q) for q in plan)


def score(plan, old, urgent):
    """Higher is better, compared in order: urgent, routine, fewer changes, less energy."""
    urgent_pts = sum(p["priority"] for p in plan if p["target"] == urgent)
    routine_pts = sum(p["priority"] for p in plan) - urgent_pts
    changes = 0 if old is None else len({p["id"] for p in plan} ^ {p["id"] for p in old})
    energy = sum(p["energy"] for p in plan)
    return (urgent_pts, routine_pts, -changes, -energy)


def search(free, fixed, options, budget, old, urgent):
    """Exact search: for each free target, skip it or pick one of its passes."""
    best = [None, None]

    def go(i, plan):
        if i == len(free):
            s = score(plan, old, urgent)
            if best[0] is None or s > best[0]:
                best[0], best[1] = s, plan
            return
        go(i + 1, plan)  # skip this target
        for p in options.get(free[i], []):
            if fits(plan, p, budget):  # prune conflicts as soon as they appear
                go(i + 1, plan + [p])

    go(0, list(fixed))
    return best[1]


def greedy(old, options, urgent, budget):
    """Add the earliest urgent pass that fits; never touch the old plan."""
    for p in sorted(options.get(urgent, []), key=lambda p: p["start"]):
        if fits(old, p, budget):
            return old + [p], ""
    return old, ""


def restricted(old, frozen, options, urgent, budget):
    """Unlock the urgent target plus the 3 most related planned targets, grow by 3 if needed."""
    frozen_ids = {p["id"] for p in frozen}
    movable = [p for p in old if p["id"] not in frozen_ids]
    urgent_passes = options.get(urgent, [])

    def link(p):  # smaller = more related: time overlap, same satellite, then closeness
        return (not any(clash(p, u) for u in urgent_passes),
                not any(p["satellite"] == u["satellite"] for u in urgent_passes),
                min((abs(p["start"] - u["start"]) for u in urgent_passes), default=0))

    ranked = sorted({p["target"] for p in movable},
                    key=lambda t: min(link(p) for p in movable if p["target"] == t))
    k = 0
    while True:
        k = min(k + 3, len(ranked))
        unlocked = ranked[:k]
        fixed = frozen + [p for p in movable if p["target"] not in unlocked]
        plan = search([urgent] + unlocked, fixed, options, budget, old, urgent)
        if k == len(ranked) or any(p["target"] == urgent for p in plan):
            return plan, f"(unlocked {k} of {len(ranked)} planned targets)"


def full(old, frozen, options, urgent, budget):
    """Reference optimum: every target that is not frozen may change."""
    free = [urgent] + sorted(t for t in options if t != urgent)
    return search(free, frozen, options, budget, old, urgent), ""


def milp_plan(old, frozen, options, urgent, budget):
    """Full-horizon MILP: four solves, one per objective, each locking in the previous result."""
    cand = [p for t in options for p in options[t]]
    n = len(cand)
    if n == 0:
        return list(frozen), ""
    old_ids = {p["id"] for p in old}
    rows, lo, hi = [], [], []

    def add(row, low, high):
        rows.append(row), lo.append(low), hi.append(high)

    for t in options:  # at most one pass per target
        add([int(p["target"] == t) for p in cand], 0, 1)
    for s in {p["satellite"] for p in cand}:  # energy left after frozen passes
        used = sum(q["energy"] for q in frozen if q["satellite"] == s)
        add([p["energy"] if p["satellite"] == s else 0 for p in cand], 0, budget - used)
    for i in range(n):  # no overlaps on a satellite
        for j in range(i + 1, n):
            if clash(cand[i], cand[j]):
                row = [0] * n
                row[i] = row[j] = 1
                add(row, 0, 1)
    upper = [0 if any(clash(p, q) for q in frozen) else 1 for p in cand]

    # Weights to maximize, in priority order: urgent, routine, keep old passes / avoid new ones, low energy.
    goals = [[p["priority"] if p["target"] == urgent else 0 for p in cand],
             [p["priority"] if p["target"] != urgent else 0 for p in cand],
             [1 if p["id"] in old_ids else -1 for p in cand],
             [-p["energy"] for p in cand]]
    for w in goals:
        res = milp(-np.array(w, dtype=float), integrality=np.ones(n),
                   bounds=Bounds(0, upper),
                   constraints=LinearConstraint(np.array(rows, dtype=float), lo, hi))
        if res.status != 0:
            raise RuntimeError("MILP failed: " + res.message)
        add(w, round(-res.fun) - 0.5, np.inf)  # later goals may not worsen this one
    return list(frozen) + [cand[i] for i in range(n) if res.x[i] > 0.5], ""


def setup(passes, urgent, now, deadline, budget):
    """Issued plan (urgent target withheld), frozen passes, and the passes that may still change."""
    routine = group([p for p in passes if p["target"] != urgent])
    old = search(sorted(routine), [], routine, budget, None, None)
    frozen = [p for p in old if p["start"] < now + FREEZE]
    frozen_targets = {p["target"] for p in frozen}
    options = group([p for p in passes
                     if p["start"] >= now + FREEZE
                     and p["target"] not in frozen_targets
                     and not (p["target"] == urgent and p["end"] > deadline)])
    return old, frozen, options


METHODS = [("Greedy", lambda old, frozen, options, urgent, budget: greedy(old, options, urgent, budget)),
           ("Restricted", restricted),
           ("Full search", full),
           ("Full MILP", milp_plan)]


def check(plan, passes, frozen, urgent, now, deadline, budget):
    """Return a list of rule violations (empty list = valid plan)."""
    problems = []
    real = {p["id"]: p for p in passes}
    for p in plan:
        if real.get(p["id"]) != p:
            problems.append(f"pass {p['id']} is not a candidate")
    targets = [p["target"] for p in plan]
    for t in set(targets):
        if targets.count(t) > 1:
            problems.append(f"target {t} imaged more than once")
    for i, a in enumerate(plan):
        for b in plan[i + 1:]:
            if clash(a, b):
                problems.append(f"passes {a['id']} and {b['id']} overlap on {a['satellite']}")
    for s in {p["satellite"] for p in plan}:
        used = sum(p["energy"] for p in plan if p["satellite"] == s)
        if used > budget:
            problems.append(f"satellite {s} uses {used} > budget {budget}")
    ids = {p["id"] for p in plan}
    for p in frozen:
        if p["id"] not in ids:
            problems.append(f"frozen pass {p['id']} was removed")
    frozen_ids = {p["id"] for p in frozen}
    for p in plan:
        if p["id"] not in frozen_ids and p["start"] < now + FREEZE:
            problems.append(f"pass {p['id']} starts inside the freeze window")
        if p["target"] == urgent and p["end"] > deadline:
            problems.append(f"urgent pass {p['id']} ends after the deadline")
    return problems


def show(name, plan, old, urgent, seconds, note):
    urgent_pts, routine_pts, neg_changes, neg_energy = score(plan, old, urgent)
    print(f"{name:11} urgent {'met' if urgent_pts else 'MISSED':6} routine {routine_pts:3}  "
          f"changes {-neg_changes}  energy {-neg_energy:2}  {seconds * 1000:7.2f} ms {note}")
    old_ids, new_ids = {p["id"] for p in old}, {p["id"] for p in plan}
    for p in old:
        if p["id"] not in new_ids:
            print(f"    removed {p['target']} on {p['satellite']} {p['start']}-{p['end']}")
    for p in plan:
        if p["id"] not in old_ids:
            print(f"    added   {p['target']} on {p['satellite']} {p['start']}-{p['end']}")


def main():
    args = sys.argv[1:] + [None] * 5
    path = args[0] or "passes.csv"
    urgent = args[1] or "FLOOD"
    now = int(args[2] or 90)
    deadline = int(args[3] or 150)
    budget = int(args[4] or 12)

    passes = load(path)
    old, frozen, options = setup(passes, urgent, now, deadline, budget)
    print(f"Issued plan: {len(old)} observations, routine priority {score(old, None, urgent)[1]}")
    print(f"Alert at {now}: {urgent} must finish by {deadline}\n")

    for name, method in METHODS:
        start = time.perf_counter()
        plan, note = method(old, frozen, options, urgent, budget)
        seconds = time.perf_counter() - start
        show(name, plan, old, urgent, seconds, note)
        for problem in check(plan, passes, frozen, urgent, now, deadline, budget):
            print("    INVALID:", problem)


if __name__ == "__main__":
    main()
