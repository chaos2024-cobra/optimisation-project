"""Replay random alerts on a CSV dataset, check every plan, and write validation.csv.

Usage: python validate.py [passes.csv] [number_of_alerts] [output.csv]
"""
import csv
import random
import sys
import time
from statistics import median

from scheduler import FREEZE, METHODS, check, load, score, setup

SEED = 1
BUDGETS = (10, 12, 14)


def main():
    args = sys.argv[1:] + [None] * 3
    path = args[0] or "passes.csv"
    n_alerts = int(args[1] or 20)
    out = args[2] or "validation.csv"

    passes = load(path)
    targets = sorted({p["target"] for p in passes})
    rng = random.Random(SEED)  # fixed seed -> same alerts every run

    rows, valid_count = [], 0
    for case in range(n_alerts):
        urgent = rng.choice(targets)
        target_pass = rng.choice([p for p in passes if p["target"] == urgent])
        now = rng.randrange(0, max(1, target_pass["start"] - FREEZE))  # alert before a usable pass
        deadline = target_pass["end"] + rng.randrange(0, 40)
        budget = rng.choice(BUDGETS)
        old, frozen, options = setup(passes, urgent, now, deadline, budget)

        results = {}
        for name, method in METHODS:
            times = []
            for _ in range(3):
                start = time.perf_counter()
                plan, note = method(old, frozen, options, urgent, budget)
                times.append((time.perf_counter() - start) * 1000)
            problems = check(plan, passes, frozen, urgent, now, deadline, budget)
            results[name] = (plan, score(plan, old, urgent), problems, median(times), note)

        best = results["Full MILP"][1]
        for name, (plan, s, problems, ms, note) in results.items():
            valid_count += not problems
            rows.append({"case": case, "target": urgent, "alert": now, "deadline": deadline,
                         "budget": budget, "method": name, "urgent_met": int(s[0] > 0),
                         "routine_priority": s[1], "edits": -s[2], "energy": -s[3],
                         "valid": int(not problems), "matches_milp": int(s == best),
                         "median_ms": round(ms, 4)})

    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} results written to {out}; {valid_count}/{len(rows)} plans valid\n")
    print(f"{'Method':12} {'Deadlines met':>13} {'Matches MILP':>13} {'Median ms':>10}")
    for name, _ in METHODS:
        mine = [r for r in rows if r["method"] == name]
        print(f"{name:12} {sum(r['urgent_met'] for r in mine):>9}/{len(mine):<3} "
              f"{sum(r['matches_milp'] for r in mine):>9}/{len(mine):<3} "
              f"{median(r['median_ms'] for r in mine):>10.3f}")


if __name__ == "__main__":
    main()
