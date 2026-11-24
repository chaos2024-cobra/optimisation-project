"""Turn results/*.csv into the figures used in the report."""
import csv
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = list(csv.DictReader(open("results/sweeps.csv")))
sc = list(csv.DictReader(open("results/scaling.csv")))
M = ["greedy", "greedy+evict", "restricted", "milp"]
sty = {"greedy": ("tab:gray", "x", "--"), "greedy+evict": ("tab:orange", "s", "-."),
       "restricted": ("tab:blue", "o", "-"), "milp": ("k", "^", ":")}


def series(sweep, key, m):
    r = [x for x in rows if x["sweep"] == sweep and x["method"] == m]
    return [float(x["value"]) for x in r], [float(x[key]) for x in r]


def panel(ax, sweep, key, ylabel, xlabel, methods=M):
    for m in methods:
        x, y = series(sweep, key, m)
        c, mk, ls = sty[m]
        ax.plot(x, y, color=c, marker=mk, ls=ls, label=m)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.grid(alpha=.3)


fig, axs = plt.subplots(2, 3, figsize=(13, 7))
panel(axs[0, 0], "lead", "urgent_met", "urgent requests met", "deadline lead time")
panel(axs[0, 1], "load", "urgent_met", "urgent requests met", "routine targets N")
panel(axs[0, 2], "energy", "urgent_met", "urgent requests met", "energy tightness $\\kappa$")
panel(axs[1, 0], "lead", "routine_gap", "routine priority lost vs MILP", "deadline lead time", M[1:])
panel(axs[1, 1], "load", "routine_gap", "routine priority lost vs MILP", "routine targets N", M[1:])
panel(axs[1, 2], "energy", "routine_gap", "routine priority lost vs MILP", "energy tightness $\\kappa$", M[1:])
axs[0, 0].legend(fontsize=8)
plt.tight_layout(); plt.savefig("results/fig_quality.png", dpi=150)

fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
for m in M:
    x = [int(r["N"]) for r in sc if r["method"] == m]; y = [float(r["time_ms"]) for r in sc if r["method"] == m]
    c, mk, ls = sty[m]; axs[0].plot(x, y, color=c, marker=mk, ls=ls, label=m)
axs[0].set_yscale("log"); axs[0].set_xscale("log"); axs[0].set_xlabel("routine targets N"); axs[0].set_ylabel("replanning time (ms)")
axs[0].grid(alpha=.3, which="both"); axs[0].legend(fontsize=8)
for m in ["greedy+evict", "restricted"]:
    x, y = series("lead", "changes", m); c, mk, ls = sty[m]; axs[1].plot(x, y, color=c, marker=mk, ls=ls, label=m)
x, y = series("lead", "changes", "milp"); axs[1].plot(x, y, color="k", marker="^", ls=":", label="milp")
axs[1].set_xlabel("deadline lead time"); axs[1].set_ylabel("schedule changes"); axs[1].grid(alpha=.3); axs[1].legend(fontsize=8)
plt.tight_layout(); plt.savefig("results/fig_runtime_changes.png", dpi=150)


# ------------------------------------------------------------------ LaTeX tables for the report
def get(sweep, value, m, key):
    for x in rows:
        if x["sweep"] == sweep and float(x["value"]) == value and x["method"] == m:
            return float(x[key])


lab = {"lead": "lead", "load": "$N$", "energy": "$\\kappa$"}
lines = []
for sweep, vals in [("lead", (8, 12, 20, 30, 45)), ("load", (15, 25, 40, 60)), ("energy", (0.3, 0.4, 0.55, 0.8, 1.0))]:
    for v in vals:
        g = lambda m, k: get(sweep, v, m, k)
        vv = f"{v:g}"
        lines.append(f"{lab[sweep]}={vv} & {g('greedy','urgent_met'):.2f} / {g('greedy+evict','urgent_met'):.2f} / {g('restricted','urgent_met'):.2f} / {g('milp','urgent_met'):.2f}"
                     f" & {g('greedy+evict','routine_gap'):.1f} / {g('restricted','routine_gap'):.1f}"
                     f" & {100*g('greedy+evict','match_opt'):.0f} / {100*g('restricted','match_opt'):.0f}"
                     f" & {g('greedy+evict','changes'):.1f} / {g('restricted','changes'):.1f} / {g('milp','changes'):.1f}"
                     f" & {g('restricted','time_ms'):.1f} / {g('milp','time_ms'):.1f}"
                     f" & {int(g('restricted','incomplete'))} \\\\")
    lines.append("\\midrule")
open("results/table_sweeps.tex", "w").write("\n".join(lines[:-1]).rstrip().rstrip("\\") + "\n")

sl = []
for N in sorted({int(r["N"]) for r in sc}):
    g = lambda m, k: float([r for r in sc if int(r["N"]) == N and r["method"] == m][0][k])
    sl.append(f"{N} & {int(g('milp','S'))} & {g('milp','free'):.0f} & {g('restricted','unlocked'):.1f} & {g('greedy+evict','time_ms'):.2f} & {g('restricted','time_ms'):.2f} & {g('milp','time_ms'):.0f} \\\\")
open("results/table_scaling.tex", "w").write("\n".join(sl).rstrip().rstrip("\\") + "\n")
