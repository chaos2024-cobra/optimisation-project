"""Rebuild the standalone replay from Python solver outputs."""
from dataclasses import asdict
import json
from pathlib import Path

from replan import eligible, greedy, metrics, milp_reference, scenario
from validate import DATA, repair, scenarios, validate


def replay(case, label, unit, bounds):
    local, unlocked, fallback = repair(case)
    original = tuple(p for p in case.passes if p.id in case.original)
    plans = {"Issued schedule": original, "Greedy insertion": greedy(case),
             "Restricted replanning": local, "Full-horizon MILP": milp_reference(case)}
    for name, plan in plans.items():
        if name != "Issued schedule":
            validate(case, plan, bounds)
    return {
        "label": label, "unit": unit, "alert": case.alert, "deadline": case.deadline,
        "cutoff": case.alert + case.lock, "target": case.urgent,
        "satellites": sorted(case.budgets), "unlocked": unlocked,
        "available": len(eligible(case)[1]), "fallback": fallback,
        "plans": {name: {"passes": [asdict(p) for p in plan],
                         "scores": metrics(case, plan)}
                  for name, plan in plans.items()},
    }


def main():
    case = scenario()
    bounds = {p.id: (p.start, p.end) for p in case.passes}
    records = [replay(case, "Floodplain walkthrough", "min", bounds)]
    for path in sorted(DATA.glob("*.inst")):
        for index, observed, bounds in scenarios(path, 202503, 12):
            records.append(replay(observed, f"{path.stem} · Alert {index}", "s", bounds))
    root = Path(__file__).resolve().parent
    template = (root / "demo_template.html").read_text()
    payload = json.dumps(records, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    (root / "demo.html").write_text(template.replace("/* REPLAY_DATA */", payload))
    print(f"Exported {len(records)} replay cases to demo.html.")


if __name__ == "__main__":
    main()
