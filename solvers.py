"""Solvers: greedy baselines, exact target-grouped search, full MILP, restricted replanning."""
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix
from model import overlap, score


# ================================================================ greedy
def greedy_static(P):
    """Highest-priority target first, earliest-starting feasible window."""
    sel, used = [], {s: 0.0 for s in P.budget}
    for t, ids in sorted(P.targets_of_free().items(), key=lambda kv: (-P.prio[kv[0]], kv[0])):
        for i in sorted(ids, key=lambda i: (P.obs[i].start, i)):
            o = P.obs[i]
            if used[o.sat] + o.e <= P.budget[o.sat] and not any(overlap(o, P.obs[j]) for j in sel):
                sel.append(i); used[o.sat] += o.e
                break
    return set(sel)


def greedy_alert(P, evict=False):
    """Keep the old plan; insert each urgent target (highest priority first) in the
    earliest-ending deadline-feasible window.  evict=False: only into free slots.
    evict=True : if no free slot exists, bump the cheapest conflicting routine observations."""
    sel = set(P.x0)
    used = {s: 0.0 for s in P.budget}
    for i in sel:
        used[P.obs[i].sat] += P.obs[i].e
    groups = P.targets_of_free()
    for t in sorted(P.urgent, key=lambda t: -P.prio[t]):
        cands = sorted(groups.get(t, []), key=lambda i: (P.obs[i].end, i))
        done = False
        for i in cands:
            o = P.obs[i]
            if used[o.sat] + o.e <= P.budget[o.sat] and not any(overlap(o, P.obs[j]) for j in sel):
                sel.add(i); used[o.sat] += o.e; done = True
                break
        if done or not evict:
            continue
        best = None
        for i in cands:
            o = P.obs[i]
            bump = {j for j in sel if overlap(o, P.obs[j])}
            need = used[o.sat] - sum(P.obs[j].e for j in bump) + o.e - P.budget[o.sat]
            extra = sorted((j for j in sel if P.obs[j].sat == o.sat and j not in bump),
                           key=lambda j: P.prio[P.obs[j].target])
            while need > 1e-9 and extra:
                j = extra.pop(0); bump.add(j); need -= P.obs[j].e
            if need > 1e-9:
                continue
            loss = sum(P.prio[P.obs[j].target] for j in bump)
            if best is None or loss < best[0]:
                best = (loss, i, bump)
        if best:
            _, i, bump = best
            for j in bump:
                sel.discard(j); used[P.obs[j].sat] -= P.obs[j].e
            sel.add(i); used[P.obs[i].sat] += P.obs[i].e
    return sel


# ================================================================ exact search grouped by target
def dfs_exact(P, unlocked=None, node_limit=3_000_000):
    """Branch and bound over targets.  For each unlocked target: pick one feasible window or skip.
    Observations of locked targets stay as in the previous plan.
    Lexicographic objective (urgent, routine, -changes, -energy).
    Returns (selection, info)."""
    obs = P.obs
    groups = P.targets_of_free()
    if unlocked is None:
        unlocked = set(groups)
    fixed = {i for i in P.x0 if obs[i].target not in unlocked}
    sats = list(P.budget)
    used = {s: 0.0 for s in sats}
    iv = {s: [] for s in sats}
    for i in fixed:
        o = obs[i]; used[o.sat] += o.e; iv[o.sat].append((o.start, o.end))
    x0_of = {obs[i].target: i for i in P.x0}

    order = sorted((t for t in unlocked if t in groups), key=lambda t: (t not in P.urgent, -P.prio[t], t))
    cands = []
    for t in order:
        ok = [i for i in groups[t]
              if used[obs[i].sat] + obs[i].e <= P.budget[obs[i].sat]
              and not any(a < obs[i].end and obs[i].start < b for a, b in iv[obs[i].sat])]
        ok.sort(key=lambda i: (i != x0_of.get(t), obs[i].e, i))
        cands.append(ok)
    n = len(order)
    pr = [P.prio[t] for t in order]
    isu = [t in P.urgent for t in order]
    rem_u = [0] * (n + 1); rem_r = [0] * (n + 1)
    for k in range(n - 1, -1, -1):
        has = bool(cands[k])
        rem_u[k] = rem_u[k + 1] + (pr[k] if has and isu[k] else 0)
        rem_r[k] = rem_r[k + 1] + (pr[k] if has and not isu[k] else 0)

    best = {"key": (-1, -1, float("-inf"), float("-inf")), "sel": None}
    cur = []
    nodes = [0]
    track = P.track_changes

    def rec(k, u, r, chg, en):
        nodes[0] += 1
        if nodes[0] > node_limit:
            return
        if k == n:
            key = (u, r, -chg, -en)
            if key > best["key"]:
                best["key"] = key; best["sel"] = list(cur)
            return
        if (u + rem_u[k], r + rem_r[k], -chg, -en) <= best["key"]:
            return
        t = order[k]
        x0i = x0_of.get(t)
        for i in cands[k]:
            o = obs[i]
            if used[o.sat] + o.e > P.budget[o.sat]:
                continue
            if any(a < o.end and o.start < b for a, b in iv[o.sat]):
                continue
            c = 0 if (not track or i == x0i) else (1 if x0i is None else 2)
            used[o.sat] += o.e; iv[o.sat].append((o.start, o.end)); cur.append(i)
            rec(k + 1, u + (pr[k] if isu[k] else 0), r + (0 if isu[k] else pr[k]), chg + c, en + o.e)
            cur.pop(); iv[o.sat].pop(); used[o.sat] -= o.e
        c = 1 if (track and x0i is not None) else 0
        rec(k + 1, u, r, chg + c, en)

    rec(0, 0, 0, 0, 0)
    sel = set(fixed) | set(best["sel"] or [])
    return sel, dict(nodes=nodes[0], complete=nodes[0] <= node_limit, n_unlocked=len(order))


# ================================================================ full-horizon MILP (reference)
def milp_lex(P, time_limit=60):
    """Exact lexicographic optimum over all free observations, solved as 4 sequential MILPs (HiGHS)."""
    ids = list(P.free)
    n = len(ids)
    if n == 0:
        return set(), {}
    obs = P.obs
    col = {i: k for k, i in enumerate(ids)}
    rows, lo, hi = [], [], []
    A = lil_matrix((0, n))
    cons = []
    # one observation per target
    g = P.targets_of_free()
    for t, L in g.items():
        if len(L) > 1:
            cons.append(({col[i]: 1 for i in L}, -np.inf, 1))
    # energy
    for s in P.budget:
        d = {col[i]: obs[i].e for i in ids if obs[i].sat == s}
        if d:
            cons.append((d, -np.inf, P.budget[s]))
    # time conflicts
    for a in range(n):
        for b in range(a + 1, n):
            if overlap(obs[ids[a]], obs[ids[b]]) and obs[ids[a]].target != obs[ids[b]].target:
                cons.append(({a: 1, b: 1}, -np.inf, 1))
    M = lil_matrix((len(cons), n)); L_, U_ = [], []
    for r, (d, l, u) in enumerate(cons):
        for c, v in d.items():
            M[r, c] = v
        L_.append(l); U_.append(u)
    base = [LinearConstraint(M.tocsr(), L_, U_)] if cons else []
    x0 = np.array([1.0 if i in P.x0 else 0.0 for i in ids])
    c_u = np.array([P.prio[obs[i].target] if obs[i].target in P.urgent else 0 for i in ids], float)
    c_r = np.array([P.prio[obs[i].target] if obs[i].target not in P.urgent else 0 for i in ids], float)
    c_ch = (1 - 2 * x0) if P.track_changes else np.zeros(n)   # changes = |x0| + sum(c_ch * x)
    c_en = np.array([obs[i].e for i in ids], float)
    stages = [(-c_u, c_u), (-c_r, c_r), (c_ch, None), (c_en, None)]
    extra, x = [], None
    for k, (c, _) in enumerate(stages):
        res = milp(c, constraints=base + extra, integrality=np.ones(n), bounds=Bounds(0, 1),
                   options=dict(time_limit=time_limit))
        if res.x is None:
            break
        x = np.round(res.x)
        val = float(c @ x)
        if val != 0 or k < 3:
            extra.append(LinearConstraint(c.reshape(1, -1), -np.inf, val + 0.5))
    sel = {ids[k] for k in range(n) if x is not None and x[k] > 0.5}
    return sel, {}


# ================================================================ restricted replanning
def _overlap_targets(P, cand_ids, others):
    out = set()
    for i in cand_ids:
        for j in others:
            if overlap(P.obs[i], P.obs[j]):
                out.add(P.obs[j].target)
    return out


def unlock_sets(P):
    """Return the unlocked target sets for levels 1, 2, 3, ... (nested)."""
    g = P.targets_of_free()
    ucand = [i for t in P.urgent for i in g.get(t, [])]
    planned = list(P.x0)
    # level 1: urgent + planned commitments in time conflict + energy-linked commitments
    L1 = set(P.urgent) & set(g)
    L1 |= _overlap_targets(P, ucand, planned)
    slack = {s: P.budget[s] - sum(P.obs[i].e for i in planned if P.obs[i].sat == s) for s in P.budget}
    for i in ucand:
        o = P.obs[i]
        if slack[o.sat] < o.e:                       # energy-blocked: link all commitments on that satellite
            L1 |= {P.obs[j].target for j in planned if P.obs[j].sat == o.sat}
    levels = [L1]
    allf = set(g)
    for _ in range(2):
        cur = levels[-1]
        cc = [i for t in cur for i in g.get(t, [])]
        nxt = set(cur) | _overlap_targets(P, cc, P.free)
        levels.append(nxt & allf)
    return levels


def restricted_replan(P, node_limit=500_000):
    """Exact search on a small unlocked set; widen the set until all urgent requests are scheduled."""
    levels = unlock_sets(P)
    allf = set(P.targets_of_free())
    info = {}
    sel = set(P.x0)
    for lv, U in enumerate(levels, 1):
        sel, info = dfs_exact(P, U, node_limit)
        info["level"] = lv
        if score(P, sel)["urgent_met"] == len(P.urgent) or U >= allf:
            break
    return sel, info


def timed(f, *a, **k):
    t0 = time.perf_counter()
    r = f(*a, **k)
    return r, time.perf_counter() - t0
