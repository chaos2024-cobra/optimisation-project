"""Alert-simulation experiments.  Usage:  python run_experiments.py [--seeds 100] [--quick]
Writes results/sweeps.csv, results/scaling.csv."""
import argparse, csv, random, statistics as st
from model import make_instance, make_alert, score
from solvers import greedy_alert, restricted_replan, milp_lex, timed

METHODS = ["greedy", "greedy+evict", "restricted", "milp"]


def one(seed, N=30, S=4, kappa=0.55, lead=25, H=150, n_urgent=2, K=3):
    inst, P0 = make_instance(seed, S=S, N=N, K=K, H=H, kappa=kappa)
    plan, _ = milp_lex(P0)                                   # previous (static optimal) plan
    rng = random.Random(seed * 7 + 1)
    T = rng.randint(10, H - 70)
    P = make_alert(inst, plan, rng, T, lead, n_urgent=n_urgent, k_urgent=2)
    base = score(P, P.x0)["routine"]                          # routine priority of the old plan (incl. frozen)
    res = {}
    for m, f in [("greedy", lambda: greedy_alert(P)), ("greedy+evict", lambda: greedy_alert(P, True)),
                 ("restricted", lambda: restricted_replan(P)), ("milp", lambda: milp_lex(P))]:
        r, t = timed(f)
        sel, info = (r if isinstance(r, tuple) else (r, {}))
        s = score(P, sel)
        res[m] = dict(urgent_met=s["urgent_met"] / len(P.urgent), urgent=s["urgent"], routine=s["routine"],
                      changes=s["changes"], energy=s["energy"], time=t,
                      level=info.get("level", 0), unlocked=info.get("n_unlocked", 0),
                      complete=info.get("complete", True), free=len(P.free))
    return res


SWEEPS = {
    "lead":  [("lead", v) for v in (8, 12, 20, 30, 45)],
    "load":  [("N", v) for v in (15, 25, 40, 60)],
    "energy": [("kappa", v) for v in (0.3, 0.4, 0.55, 0.8, 1.0)],
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seeds", type=int, default=60)
    ap.add_argument("--quick", action="store_true"); a = ap.parse_args()
    n = 10 if a.quick else a.seeds
    rows = []
    for sweep, vals in SWEEPS.items():
        for key, v in vals:
            R = [one(s, **{key: v}) for s in range(n)]
            for m in METHODS:
                g = lambda k: [r[m][k] for r in R]
                opt_u = [r["milp"]["urgent"] for r in R]; opt_r = [r["milp"]["routine"] for r in R]
                match = [r[m]["urgent"] == r["milp"]["urgent"] and r[m]["routine"] == r["milp"]["routine"] for r in R]
                rows.append(dict(sweep=sweep, param=key, value=v, method=m, n=n,
                                 urgent_met=st.mean(g("urgent_met")), routine=st.mean(g("routine")),
                                 routine_gap=st.mean([o - r[m]["routine"] for o, r in zip(opt_r, R)]),
                                 changes=st.mean(g("changes")), energy=st.mean(g("energy")),
                                 time_ms=1000 * st.mean(g("time")), match_opt=st.mean(match),
                                 level=st.mean(g("level")), unlocked=st.mean(g("unlocked")),
                                 free=st.mean(g("free")), incomplete=sum(1 for c in g("complete") if not c)))
            print(sweep, key, v, "done", flush=True)
    with open("results/sweeps.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    # scaling with constant density (targets per satellite fixed)
    rows = []
    for N in (30, 60, 120, 240):
        S = max(4, round(N / 7.5))
        R = [one(s, N=N, S=S, n_urgent=2) for s in range(5 if a.quick else 10)]
        for m in METHODS:
            rows.append(dict(N=N, S=S, method=m, time_ms=1000 * st.mean(r[m]["time"] for r in R),
                             free=st.mean(r[m]["free"] for r in R), unlocked=st.mean(r[m]["unlocked"] for r in R),
                             match_opt=st.mean(r[m]["urgent"] == r["milp"]["urgent"] and r[m]["routine"] == r["milp"]["routine"] for r in R)))
        print("scaling", N, "done", flush=True)
    with open("results/scaling.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
