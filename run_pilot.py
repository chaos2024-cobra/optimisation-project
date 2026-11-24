"""Static pilot: 2 satellites, 6 targets, 12 windows.  Compares greedy, exact target-grouped search,
MILP and brute-force enumeration (the same four checks as in the proposal)."""
import itertools
from model import Obs, Problem, score, is_feasible
from solvers import greedy_static, dfs_exact, milp_lex

prio = {0: 5, 1: 10, 2: 7, 3: 5, 4: 4, 5: 5}
budget = {0: 8, 1: 8}
# (id, sat, target, start, end, energy)
W = [(0, 0, 0, 1, 4, 4), (1, 1, 0, 9, 12, 3), (2, 0, 1, 8, 12, 2), (3, 1, 1, 7, 11, 3),
     (4, 0, 2, 5, 7, 3), (5, 1, 2, 9, 11, 2), (6, 0, 3, 11, 13, 2), (7, 1, 3, 4, 8, 4),
     (8, 0, 4, 0, 2, 2), (9, 1, 4, 7, 10, 2), (10, 0, 5, 6, 8, 3), (11, 1, 5, 6, 10, 3)]
obs = {w[0]: Obs(*w) for w in W}
P = Problem(obs, prio, set(), budget, set(), sorted(obs), set(), False)

best = None
for r in range(len(W) + 1):                       # brute force over all 2^12 subsets
    for c in itertools.combinations(P.free, r):
        if is_feasible(P, c):
            s = score(P, c); k = (s["routine"], -s["energy"])
            if best is None or k > best:
                best = k
for name, sel in [("Greedy", greedy_static(P)), ("Exact search", dfs_exact(P)[0]), ("MILP", milp_lex(P)[0])]:
    s = score(P, sel)
    print(f"{name:13s} targets={s['n_targets']}  priority={s['routine']}  energy={s['energy']}  feasible={is_feasible(P, sel)}")
print(f"Brute force   priority={best[0]}  energy={-best[1]}")
