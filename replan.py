"""Fixed-window scheduling for a single urgent Earth-observation request."""
from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import combinations
import argparse
import csv
from time import perf_counter

try:
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
except ModuleNotFoundError as exc:
    if exc.name not in {"numpy", "scipy"}:
        raise
    milp = None


@dataclass(frozen=True)
class Pass:
    id: str
    satellite: str
    target: str
    start: int
    end: int
    priority: int
    energy: int


@dataclass(frozen=True)
class Scenario:
    passes: tuple
    original: frozenset
    budgets: dict
    alert: int
    lock: int
    deadline: int
    urgent: str


def scenario():
    return Scenario((
        Pass("C1", "Sat-A", "Coast", 0, 3, 4, 1),
        Pass("F1", "Sat-A", "Forest", 8, 12, 8, 3),
        Pass("F2", "Sat-B", "Forest", 9, 12, 8, 2),
        Pass("R1", "Sat-B", "Reservoir", 5, 8, 6, 2),
        Pass("W1", "Sat-B", "Wetland", 13, 16, 5, 2),
        Pass("U1", "Sat-A", "Floodplain", 9, 11, 15, 4),
        Pass("U2", "Sat-B", "Floodplain", 14, 16, 15, 3),
    ), frozenset(("C1", "F1", "R1", "W1")), {"Sat-A": 8, "Sat-B": 6},
        alert=4, lock=2, deadline=12, urgent="Floodplain")


def overlaps(a, b):
    return a.satellite == b.satellite and max(a.start, b.start) < min(a.end, b.end)


def eligible(case):
    cutoff = case.alert + case.lock
    fixed = tuple(p for p in case.passes if p.id in case.original and p.start < cutoff)
    choices = tuple(p for p in case.passes if p.start >= cutoff
                    and (p.target != case.urgent or p.end <= case.deadline))
    return fixed, choices


def feasible(case, schedule, candidate):
    return (all(p.target != candidate.target and not overlaps(p, candidate) for p in schedule)
            and candidate.energy + sum(p.energy for p in schedule
                                       if p.satellite == candidate.satellite)
            <= case.budgets[candidate.satellite])


def metrics(case, schedule):
    ids = {p.id for p in schedule}
    return (
        sum(p.priority for p in schedule if p.target == case.urgent),
        sum(p.priority for p in schedule if p.target != case.urgent),
        -len(ids ^ case.original),
        -sum(p.energy for p in schedule),
    )


def greedy(case):
    _, choices = eligible(case)
    schedule = [p for p in case.passes if p.id in case.original]
    for p in sorted(choices, key=lambda p: (p.start, p.end, p.id)):
        if p.target == case.urgent and feasible(case, schedule, p):
            schedule.append(p)
            break
    return tuple(schedule)


def target_search(case, fixed, choices):
    groups = defaultdict(list)
    for p in choices:
        groups[p.target].append(p)
    ordered = sorted(groups.values(), key=lambda group: (
        group[0].target != case.urgent, len(group), group[0].target))
    best = tuple(fixed)
    best_score = metrics(case, best)
    schedule = list(fixed)

    def search(index):
        nonlocal best, best_score
        if index == len(ordered):
            score = metrics(case, schedule)
            if score > best_score:
                best, best_score = tuple(schedule), score
            return
        for p in ordered[index]:
            if feasible(case, schedule, p):
                schedule.append(p)
                search(index + 1)
                schedule.pop()
        search(index + 1)

    search(0)
    return best


def restricted(case):
    fixed, choices = eligible(case)
    urgent = tuple(p for p in choices if p.target == case.urgent)
    if not urgent:
        return greedy(case), 0, False
    routine = tuple(p for p in choices if p.target != case.urgent)
    committed = [p for p in routine if p.id in case.original]
    urgent_satellites = {p.satellite for p in urgent}
    affected = {p.target for p in committed if any(overlaps(p, u) for u in urgent)}
    affected.update(p.target for p in committed if p.satellite in urgent_satellites)
    unlocked = tuple(p for p in choices if p.target in affected or p.target == case.urgent)
    frozen = fixed + tuple(p for p in committed if p.target not in affected)
    result = target_search(case, frozen, unlocked)
    if not metrics(case, result)[0] and len(unlocked) < len(choices):
        return target_search(case, fixed, choices), len(choices), True
    return result, len(unlocked), False


def enumerate_reference(case):
    """Independent subset reference for small instances without SciPy."""
    fixed, choices = eligible(case)
    if len(choices) > 22:
        raise ValueError("Install SciPy for the full reference on larger instances.")
    best = fixed
    for count in range(len(choices) + 1):
        for chosen in combinations(choices, count):
            schedule = fixed + chosen
            if len({p.target for p in schedule}) != len(schedule):
                continue
            if any(overlaps(a, b) for a, b in combinations(schedule, 2)):
                continue
            if any(sum(p.energy for p in schedule if p.satellite == sat) > limit
                   for sat, limit in case.budgets.items()):
                continue
            if metrics(case, schedule) > metrics(case, best):
                best = schedule
    return best


def milp_reference(case):
    fixed, choices = eligible(case)
    candidates = fixed + choices
    n = len(candidates)
    if not n:
        return ()
    rows, lower, upper = [], [], []

    def constraint(row, maximum, minimum=-np.inf):
        rows.append(row)
        lower.append(minimum)
        upper.append(maximum)

    for target in sorted({p.target for p in candidates}):
        constraint([int(p.target == target) for p in candidates], 1)
    for sat, budget in case.budgets.items():
        constraint([p.energy if p.satellite == sat else 0 for p in candidates], budget)
    for i, j in combinations(range(n), 2):
        if overlaps(candidates[i], candidates[j]):
            constraint([int(k in (i, j)) for k in range(n)], 1)

    objectives = [
        [-p.priority if p.target == case.urgent else 0 for p in candidates],
        [-p.priority if p.target != case.urgent else 0 for p in candidates],
        [-1 if p.id in case.original else 1 for p in candidates],
        [p.energy for p in candidates],
    ]
    for objective in objectives:
        result = milp(
            objective, integrality=np.ones(n),
            bounds=Bounds([1] * len(fixed) + [0] * len(choices), np.ones(n)),
            constraints=LinearConstraint(rows, lower, upper),
            options={"mip_rel_gap": 0.0},
        )
        if not result.success:
            raise RuntimeError(result.message)
        value = round(result.fun)
        constraint(objective, value, value)
    return tuple(p for p, selected in zip(candidates, result.x) if selected > 0.5)


def reference(case):
    if milp is None:
        return "Full-horizon enumeration", enumerate_reference(case)
    return "Full-horizon MILP", milp_reference(case)


def compare(case):
    results = []
    start = perf_counter()
    plan = greedy(case)
    results.append(("Greedy insertion", plan, (perf_counter() - start) * 1000))
    start = perf_counter()
    plan, unlocked, expanded = restricted(case)
    results.append(("Restricted replanning", plan, (perf_counter() - start) * 1000))
    start = perf_counter()
    label, plan = reference(case)
    results.append((label, plan, (perf_counter() - start) * 1000))
    return results, unlocked, expanded


def timeline(plan):
    for sat in sorted({p.satellite for p in plan}):
        passes = sorted((p for p in plan if p.satellite == sat), key=lambda p: p.start)
        print(f"  {sat}: " + " | ".join(f"{p.start:02d}-{p.end:02d} {p.target}" for p in passes))


def benchmark(path):
    base = scenario()
    with open(path, "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["deadline", "lock_minutes", "sat_a_budget", "forest_alt_start",
                         "method", "urgent_met", "urgent_priority", "routine_priority",
                         "changes", "energy", "runtime_ms", "restricted_candidates", "expanded"])
        for deadline in (10, 12, 16):
            for lock in (0, 2, 5):
                for energy in (5, 8):
                    for alternate in (7, 9):
                        passes = tuple(replace(p, start=alternate, end=alternate + 3)
                                       if p.id == "F2" else p for p in base.passes)
                        case = replace(base, passes=passes, deadline=deadline, lock=lock,
                                       budgets={**base.budgets, "Sat-A": energy})
                        results, unlocked, expanded = compare(case)
                        for label, plan, milliseconds in results:
                            u, r, d, e = metrics(case, plan)
                            writer.writerow([deadline, lock, energy, alternate, label,
                                             int(u > 0), u, r, -d, -e, f"{milliseconds:.4f}",
                                             unlocked, expanded])
    print(f"Wrote 36 scenarios and 108 result rows to {path}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline", type=int, default=12)
    parser.add_argument("--benchmark", metavar="CSV")
    args = parser.parse_args()
    if args.benchmark:
        benchmark(args.benchmark)
        return
    case = replace(scenario(), deadline=args.deadline)
    print("FLOOD MAPPING ALERT")
    print(f"Alert minute {case.alert} | Freeze through starts before minute "
          f"{case.alert + case.lock} | Floodplain due by minute {case.deadline}")
    print("\nOriginal schedule")
    timeline([p for p in case.passes if p.id in case.original])
    results, unlocked, expanded = compare(case)
    for label, plan, ms in results:
        u, r, d, e = metrics(case, plan)
        print(f"\n{label} | Floodplain {'MET' if u else 'MISSED'} | "
              f"Routine priority {r} | Changes {-d} | Energy {-e} | {ms:.2f} ms")
        timeline(plan)
    print(f"\nRestricted search: {unlocked} adjustable opportunities"
          f" out of {len(eligible(case)[1])}; expanded: {expanded}.")


if __name__ == "__main__":
    main()
