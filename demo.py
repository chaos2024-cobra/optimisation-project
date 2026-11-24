"""Live demo: one alert on a small instance.  Prints the schedules and saves results/demo_gantt.png.
Usage: python demo.py [seed]   (default: first seed where greedy+evict loses routine coverage that restricted keeps)"""
import random, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from model import make_instance, make_alert, score
from solvers import greedy_alert, restricted_replan, milp_lex, dfs_exact


def build(seed):
    inst, P0 = make_instance(seed, S=3, N=12, K=3, H=60, kappa=0.6)
    plan, _ = dfs_exact(P0)
    rng = random.Random(seed)
    P = make_alert(inst, plan, rng, T=rng.randint(5, 20), lead=14, freeze=3, n_urgent=1, k_urgent=3)
    return inst, plan, P


def pick():
    for seed in range(500):
        inst, plan, P = build(seed)
        g, e = greedy_alert(P), greedy_alert(P, True)
        r, _ = restricted_replan(P); m, _ = milp_lex(P)
        sg, se, sr, sm = (score(P, x) for x in (g, e, r, m))
        if (sg["urgent_met"] == 0 and sr["urgent_met"] == 1 and sr["routine"] >= se["routine"] + 4
                and (sr["urgent"], sr["routine"]) == (sm["urgent"], sm["routine"])):
            return seed
    return 0


def gantt(ax, P, plan_sel, title):
    cols = {}
    for k, i in enumerate(sorted(P.frozen | set(plan_sel), key=lambda i: P.obs[i].start)):
        o = P.obs[i]
        urgent = o.target in P.urgent
        color = "#d62728" if urgent else ("#999999" if i in P.frozen else "#1f77b4")
        ax.barh(o.sat, o.end - o.start, left=o.start, height=0.6, color=color, edgecolor="k")
        ax.text((o.start + o.end) / 2, o.sat, f"T{o.target}", ha="center", va="center", color="w", fontsize=8)
    ax.set_yticks(sorted(P.budget)); ax.set_yticklabels([f"Sat {s}" for s in sorted(P.budget)])
    ax.set_title(title, fontsize=10); ax.set_xlabel("time")


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else pick()
    inst, plan, P = build(seed)
    old = set(plan) & set(P.free)
    sols = {"Previous plan (before alert)": old, "Greedy insertion": greedy_alert(P),
            "Greedy + evict": greedy_alert(P, True), "Restricted replanning": restricted_replan(P)[0],
            "Full MILP (reference)": milp_lex(P)[0]}
    print(f"seed={seed}  urgent targets={sorted(P.urgent)}  frozen={sorted(P.frozen)}")
    for name, sel in sols.items():
        s = score(P, sel)
        print(f"{name:30s} urgent met={s['urgent_met']}/{len(P.urgent)}  routine priority={s['routine']:3d}  "
              f"changes={s['changes']}  energy={s['energy']}")
    fig, axs = plt.subplots(len(sols), 1, figsize=(9, 11), sharex=True)
    for ax, (name, sel) in zip(axs, sols.items()):
        gantt(ax, P, sel, name)
    fig.text(0.5, 0.005, "grey = frozen, blue = routine, red = urgent", ha="center", fontsize=9)
    plt.tight_layout(); plt.savefig("results/demo_gantt.png", dpi=150)
