"""Replay deterministic alerts on three published IAEOSSP instances."""
import argparse
from collections import Counter
import csv
from dataclasses import replace
from itertools import combinations
from pathlib import Path
import random
from statistics import median
from time import perf_counter

from replan import Pass, Scenario, eligible, greedy, metrics, milp, milp_reference
from replan import overlaps, target_search


DATA = Path(__file__).resolve().parent / "data"


def load_instance(path):
    lines = path.read_text().splitlines()

    def values(label):
        index = next(i for i, line in enumerate(lines) if line.startswith(label))
        return list(map(int, lines[index + 1].split()))

    targets, = values("Number of targets")
    satellites, = values("Number of satellites")
    days, = values("Planning horizon")
    duration, = values("Observation-task processing time")
    priorities = values("Profit of observing")
    counts = values("Number of obervation tasks")
    windows = values("Time windows of observation tasks")
    if len(priorities) != targets or len(counts) != targets * satellites:
        raise ValueError(f"Inconsistent instance dimensions in {path}")
    if len(windows) != 3 * sum(counts):
        raise ValueError(f"Inconsistent visibility window count in {path}")

    cursor = 0
    passes = []
    bounds = {}
    for index, count in enumerate(counts):
        sat, target = divmod(index, targets)
        for _ in range(count):
            start, end, _roll = windows[cursor:cursor + 3]
            cursor += 3
            if not 0 <= start < end <= days * 86400:
                raise ValueError(f"Invalid visibility window in {path}")
            if end - start >= duration:
                middle = (start + end - duration) // 2
                identity = str(cursor // 3)
                passes.append(Pass(identity, f"S{sat + 1}", f"T{target + 1}",
                                   middle, middle + duration, priorities[target], duration))
                bounds[identity] = (start, end)
    return tuple(passes), bounds, days, duration


def validate(case, plan, bounds):
    fixed, choices = eligible(case)
    ids = {p.id for p in plan}
    if not set(fixed) <= set(plan) <= set(fixed + choices):
        raise AssertionError("Ineligible opportunity selected or freeze violated")
    if len(ids) != len(plan) or len({p.target for p in plan}) != len(plan):
        raise AssertionError("Duplicated observation or target")
    if any(overlaps(a, b) for a, b in combinations(plan, 2)):
        raise AssertionError("Overlapping observations")
    for sat, cap in case.budgets.items():
        if sum(p.energy for p in plan if p.satellite == sat) > cap:
            raise AssertionError("Energy budget exceeded")
    for p in plan:
        lo, hi = bounds[p.id]
        if not lo <= p.start < p.end <= hi:
            raise AssertionError("Observation leaves visibility window")
        if p.target == case.urgent and p.end > case.deadline:
            raise AssertionError("Urgent deadline exceeded")


def repair(case):
    fixed, choices = eligible(case)
    urgent = tuple(p for p in choices if p.target == case.urgent)
    if not urgent:
        return greedy(case), 0, False
    sats = {p.satellite for p in urgent}
    committed = tuple(p for p in choices if p.id in case.original)
    linked = sorted((p for p in committed if p.satellite in sats), key=lambda p: (
        not any(overlaps(p, u) for u in urgent),
        min(abs(p.start - u.start) for u in urgent if p.satellite == u.satellite),
        p.priority, p.id,
    ))
    best = greedy(case)
    examined = 0
    for limit in (3, 6, 9):
        affected = {p.target for p in linked[:limit]} | {case.urgent}
        unlocked = tuple(p for p in choices if p.target in affected)
        if len(unlocked) == examined:
            continue
        examined = len(unlocked)
        held = fixed + tuple(p for p in committed if p.target not in affected)
        best = target_search(case, held, unlocked)
        if metrics(case, best)[0]:
            return best, examined, False
    # A missed urgent request may require a change outside the local neighborhood.
    return milp_reference(case), len(choices), True


def scenarios(path, seed, count):
    passes, bounds, days, duration = load_instance(path)
    targets = sorted({p.target for p in passes})
    rng = random.Random(seed)
    for run, target in enumerate(rng.sample(targets, min(count, len(targets)))):
        arrival_pass = rng.choice([p for p in passes if p.target == target])
        lead = (120, 600, 1800)[run % 3]
        slack = (0, 900, 3600)[(run // 3) % 3]
        alert = max(0, arrival_pass.start - lead)
        deadline = min(days * 86400, arrival_pass.end + slack)
        sats = sorted({p.satellite for p in passes})
        cap = max(duration, round(len(targets) * (0.35 if run % 2 else 0.65)
                                  / len(sats)) * duration)
        budget = dict.fromkeys(sats, cap)
        routine = tuple(p for p in passes if p.target != target)
        initial = Scenario(routine, frozenset(), budget, -1, 0, -1, "")
        issued = milp_reference(initial)
        validate(initial, issued, bounds)
        yield (run, Scenario(passes, frozenset(p.id for p in issued), budget,
                             alert, 60, deadline, target), bounds)


def measure(method, repeats):
    durations = []
    for _ in range(repeats):
        start = perf_counter()
        answer = method()
        durations.append(1000 * (perf_counter() - start))
    return answer, median(durations)


def run(output, cases, repeats):
    if milp is None:
        raise SystemExit("Install SciPy using requirements.txt before benchmark validation.")
    rows = []
    for path in sorted(DATA.glob("*.inst")):
        for index, case, bounds in scenarios(path, 202503, cases):
            (local, unlocked, fallback), local_ms = measure(lambda: repair(case), repeats)
            full, full_ms = measure(lambda: milp_reference(case), repeats)
            quick, quick_ms = measure(lambda: greedy(case), repeats)
            ref_score = metrics(case, full)
            for name, plan, elapsed, adjustable, used_fallback in (
                ("greedy", quick, quick_ms, 0, False),
                ("restricted", local, local_ms, unlocked, fallback),
                ("milp", full, full_ms, len(eligible(case)[1]), False),
            ):
                validate(case, plan, bounds)
                score = metrics(case, plan)
                if score > ref_score:
                    raise AssertionError("Feasible result exceeds MILP optimum")
                urgent, routine, changes, energy = score
                rows.append(dict(instance=path.stem, case=index, target=case.urgent,
                                 alert_s=case.alert, deadline_s=case.deadline,
                                 budget_per_satellite=next(iter(case.budgets.values())),
                                 method=name, urgent_met=int(urgent > 0),
                                 routine_priority=routine, edits=-changes, energy=-energy,
                                 adjustable=adjustable, fallback=int(used_fallback),
                                 matches_milp=int(score == ref_score), median_ms=round(elapsed, 4)))
        print(f"Validated {path.stem}", flush=True)
    with Path(output).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    for method in ("greedy", "restricted", "milp"):
        subset = [r for r in rows if r["method"] == method]
        counts = Counter(r["urgent_met"] for r in subset)
        print(f"{method:10} deadlines {counts[1]}/{len(subset)} | "
              f"exact objective matches {sum(r['matches_milp'] for r in subset)} | "
              f"fallbacks {sum(r['fallback'] for r in subset)} | "
              f"median runtime {median(r['median_ms'] for r in subset):.2f} ms")


def demo(instance, index):
    if milp is None:
        raise SystemExit("Install SciPy using requirements.txt for the dataset demo.")
    path = DATA / f"{instance}.inst"
    if not path.is_file() or index < 0:
        raise SystemExit("Choose a bundled instance and a nonnegative case index.")
    for run_index, case, bounds in scenarios(path, 202503, 12):
        if run_index != index:
            continue
        print(f"{instance}, alert {index}: {case.urgent} arrives at {case.alert}s, "
              f"due at {case.deadline}s")
        print("Original routine priority:", sum(p.priority for p in case.passes
                                               if p.id in case.original))
        by_id = {p.id: p for p in case.passes}
        local, adjustable, fallback = repair(case)
        for name, plan in (("Greedy", greedy(case)), ("Restricted", local),
                           ("Full MILP", milp_reference(case))):
            validate(case, plan, bounds)
            urgent, routine, changes, energy = metrics(case, plan)
            print(f"{name}: deadline {'met' if urgent else 'missed'}, "
                  f"routine priority {routine}, edits {-changes}, energy {-energy}")
            ids = {p.id for p in plan}
            for action, changed in (("removed", case.original - ids),
                                    ("added", ids - case.original)):
                for key in sorted(changed, key=int):
                    p = by_id[key]
                    print(f"  {action:7} {p.target}  {p.satellite}  {p.start}–{p.end}s")
        print(f"Restricted unlocked {adjustable}/{len(eligible(case)[1])} choices, "
              f"MILP fallback: {fallback}")
        return
    raise SystemExit("Dataset demo cases are numbered 0 to 11.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=12, help="alerts per instance")
    parser.add_argument("--repeats", type=int, default=3, help="timed runs per solver")
    parser.add_argument("--output", default="validation.csv")
    parser.add_argument("--demo", choices=sorted(p.stem for p in DATA.glob("*.inst")))
    parser.add_argument("--index", type=int, default=4, help="dataset demo case")
    args = parser.parse_args()
    if args.demo:
        demo(args.demo, args.index)
        raise SystemExit(0)
    if args.cases < 1 or args.repeats < 1:
        parser.error("cases and repeats must be at least 1")
    run(args.output, args.cases, args.repeats)
