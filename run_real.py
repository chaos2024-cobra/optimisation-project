"""Alert simulation on REAL satellite passes (TLE snapshot 2026-11-23, 5 EO satellites, 8 Indian flood-prone sites).
Usage: python run_real.py      (needs real/data/real_windows.csv; see README for how to generate it)
Writes results/real_sweeps.csv, results/real_scenarios.csv, results/table_real.tex"""
import csv, random, statistics as st
from model import make_alert, score
from solvers import greedy_alert, restricted_replan, milp_lex, timed
from real_data import load_passes, real_instance, urgent_windows_for

METHODS = ["greedy", "greedy+evict", "restricted", "milp"]
PASSES = {a: load_passes(max_offnadir=a)[0] for a in (20.0, 30.0, 40.0)}
CONFIGS = [("lead", 720, 0.55, 30.0), ("lead", 1440, 0.55, 30.0), ("lead", 2880, 0.55, 30.0), ("kappa", 1440, 0.4, 30.0),
           ("kappa", 1440, 0.8, 30.0), ("pointing", 1440, 0.55, 20.0), ("pointing", 1440, 0.55, 40.0)]


def scenarios(kappa, lead, off, seed=0):
    passes = PASSES[off]
    inst, P0 = real_instance(passes, kappa=kappa, seed=seed, max_offnadir=off)
    plan, _ = milp_lex(P0)
    for site in inst["sites"]:
        uw = urgent_windows_for(inst, passes, site)
        for k in range(1, 9):                         # alert every 12 h, day 0.5 ... day 4
            T = 720 * k
            P = make_alert(inst, plan, random.Random(0), T, lead, freeze=60, urgent_windows=uw)
            yield site, T, P


rows, detail = [], []
for sweep, lead, kappa, off in CONFIGS:
    R = []
    for site, T, P in scenarios(kappa, lead, off):
        res = {}
        for m, f in [("greedy", lambda: greedy_alert(P)), ("greedy+evict", lambda: greedy_alert(P, True)),
                     ("restricted", lambda: restricted_replan(P)), ("milp", lambda: milp_lex(P))]:
            r, t = timed(f); sel, info = r if isinstance(r, tuple) else (r, {})
            s = score(P, sel); res[m] = dict(s, time=t, level=info.get("level", 0), complete=info.get("complete", True))
        feasible = res["milp"]["urgent_met"] == 1
        R.append((feasible, res))
        detail.append(dict(sweep=sweep, lead_min=lead, kappa=kappa, offnadir=off, site=site, alert_min=T, feasible=feasible,
                           **{f"{m}_urgent": res[m]["urgent_met"] for m in METHODS},
                           **{f"{m}_routine": res[m]["routine"] for m in METHODS},
                           **{f"{m}_changes": res[m]["changes"] for m in METHODS}))
    F = [r for ok, r in R if ok]
    for m in METHODS:
        rows.append(dict(sweep=sweep, lead_min=lead, kappa=kappa, offnadir=off, windows=len(PASSES[off]), scenarios=len(R), feasible=len(F),
                         urgent_met=st.mean(r[m]["urgent_met"] for r in F) if F else float("nan"),
                         routine_gap=st.mean(r["milp"]["routine"] - r[m]["routine"] for r in F) if F else float("nan"),
                         match_opt=st.mean((r[m]["urgent"], r[m]["routine"]) == (r["milp"]["urgent"], r["milp"]["routine"]) for r in F) if F else float("nan"),
                         changes=st.mean(r[m]["changes"] for r in F) if F else float("nan"),
                         time_ms=1000 * st.mean(r[m]["time"] for r in F) if F else float("nan"),
                         incomplete=sum(1 for r in F if not r[m]["complete"]), method=m))
    print(sweep, lead, kappa, off, "scenarios", len(R), "feasible", len(F), flush=True)

for fn, data in (("results/real_sweeps.csv", rows), ("results/real_scenarios.csv", detail)):
    with open(fn, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

# LaTeX table
def g(sw, lead, kappa, off, m, k):
    return [r for r in rows if r["sweep"] == sw and r["lead_min"] == lead and r["kappa"] == kappa and r["offnadir"] == off and r["method"] == m][0][k]
lines = []
for sw, lead, kappa, off in CONFIGS:
    a = lambda m, k: g(sw, lead, kappa, off, m, k)
    lines.append(f"{lead//60}\\,h / {kappa} / {off:g}$^\\circ$ & {a('milp','windows')} & {int(a('milp','feasible'))}/{int(a('milp','scenarios'))}"
                 f" & {a('greedy','urgent_met'):.2f} / {a('greedy+evict','urgent_met'):.2f} / {a('restricted','urgent_met'):.2f}"
                 f" & {a('greedy+evict','routine_gap'):.1f} / {a('restricted','routine_gap'):.1f}"
                 f" & {100*a('greedy+evict','match_opt'):.0f} / {100*a('restricted','match_opt'):.0f}"
                 f" & {a('greedy+evict','changes'):.1f} / {a('restricted','changes'):.1f} / {a('milp','changes'):.1f}"
                 f" & {a('restricted','time_ms'):.1f} / {a('milp','time_ms'):.1f}")
open("results/table_real.tex", "w").write(" \\\\\n".join(lines) + "\n")
