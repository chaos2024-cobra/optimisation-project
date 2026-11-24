"""Sanity checks: brute-force enumeration == target-grouped DFS == MILP, and feasibility of all outputs."""
import random, itertools
from model import make_instance, make_alert, score, is_feasible
from solvers import dfs_exact, milp_lex, restricted_replan, greedy_alert, greedy_static


def brute(P):
    best, bsel = None, None
    free = P.free
    for r in range(len(free) + 1):
        for comb in itertools.combinations(free, r):
            if is_feasible(P, comb):
                s = score(P, comb)
                key = (s["urgent"], s["routine"], -s["changes"], -s["energy"])
                if best is None or key > best:
                    best, bsel = key, set(comb)
    return best


def key(P, sel):
    s = score(P, sel)
    return (s["urgent"], s["routine"], -s["changes"], -s["energy"])


bad = 0
checked = 0
for seed in range(60):
    inst, P0 = make_instance(seed, S=2, N=5, K=2, H=30, kappa=0.7, dur=(3, 8))
    # static check
    if len(P0.free) <= 13:
        checked += 1; b = brute(P0); d, _ = dfs_exact(P0); m, _ = milp_lex(P0)
        assert is_feasible(P0, d) and is_feasible(P0, m)
        if not (b == key(P0, d) == key(P0, m)):
            bad += 1; print("static mismatch", seed, b, key(P0, d), key(P0, m))
    # alert check
    plan, _ = dfs_exact(P0)
    rng = random.Random(seed)
    P = make_alert(inst, plan, rng, T=rng.randint(2, 10), lead=rng.choice([8, 12, 18]), freeze=2, n_urgent=1, k_urgent=2)
    if len(P.free) <= 13:
        checked += 1; b = brute(P); d, _ = dfs_exact(P); m, _ = milp_lex(P)
        assert is_feasible(P, d) and is_feasible(P, m)
        if not (b == key(P, d) == key(P, m)):
            bad += 1; print("alert mismatch", seed, b, key(P, d), key(P, m))
    for sel in (restricted_replan(P)[0], greedy_alert(P), greedy_alert(P, True)):
        assert is_feasible(P, sel), "infeasible output"
print("brute-force comparisons:", checked, " mismatches:", bad)
