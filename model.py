"""Data model, instance generator and scoring for the satellite replanning project."""
import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Obs:
    id: int
    sat: int
    target: int
    start: float
    end: float
    e: float  # energy cost


def overlap(a, b):
    return a.sat == b.sat and a.start < b.end and b.start < a.end


@dataclass
class Problem:
    """One scheduling problem (static, or the post-alert problem).

    obs     : id -> Obs for every candidate observation
    prio    : target -> priority
    urgent  : set of urgent targets (empty for the static problem)
    budget  : sat -> energy still available for the *free* observations
    frozen  : ids that are fixed in the plan (completed / imminent)
    free    : ids that may still be selected or dropped
    x0      : previous plan restricted to free ids (used for the change count)
    track_changes : False for the static problem (no previous plan)
    """
    obs: dict
    prio: dict
    urgent: set
    budget: dict
    frozen: set
    free: list
    x0: set
    track_changes: bool = True

    def targets_of_free(self):
        g = {}
        for i in self.free:
            g.setdefault(self.obs[i].target, []).append(i)
        return g


# ---------------------------------------------------------------- scoring
def score(P, sel):
    sel = set(sel)
    covered = {P.obs[i].target for i in sel | P.frozen}
    u = sum(P.prio[t] for t in covered if t in P.urgent)
    r = sum(P.prio[t] for t in covered if t not in P.urgent)
    return dict(
        urgent=u,
        routine=r,
        changes=len(sel ^ P.x0) if P.track_changes else 0,
        energy=sum(P.obs[i].e for i in sel),
        urgent_met=sum(1 for t in P.urgent if t in covered),
        n_targets=len(covered),
    )


def is_feasible(P, sel):
    sel = list(sel)
    tg = [P.obs[i].target for i in sel] + [P.obs[i].target for i in P.frozen]
    if len(tg) != len(set(tg)):
        return False
    used = {}
    for i in sel:
        o = P.obs[i]
        used[o.sat] = used.get(o.sat, 0) + o.e
    if any(used[s] > P.budget[s] + 1e-9 for s in used):
        return False
    allsel = sel + list(P.frozen)
    for a in range(len(allsel)):
        for b in range(a + 1, len(allsel)):
            if overlap(P.obs[allsel[a]], P.obs[allsel[b]]):
                return False
    return all(i in set(P.free) for i in sel)


# ---------------------------------------------------------------- instances
def make_instance(seed, S=4, N=30, K=3, H=150, kappa=0.55, dur=(3, 8), energy=(1, 5), pr=(1, 10)):
    """Random static instance: N targets, each with up to K visibility windows on distinct satellites.
    kappa scales the per-satellite energy budget (smaller = tighter)."""
    rng = random.Random(seed)
    obs, prio, nid = {}, {}, 0
    for t in range(N):
        prio[t] = rng.randint(*pr)
        k = rng.randint(max(1, K - 1), K)
        for s in rng.sample(range(S), min(k, S)):
            d = rng.randint(*dur)
            st = rng.randint(0, H - d)
            obs[nid] = Obs(nid, s, t, st, st + d, rng.randint(*energy))
            nid += 1
    tot = {s: 0.0 for s in range(S)}
    for o in obs.values():
        tot[o.sat] += o.e
    avg_k = len(obs) / N
    budget = {s: round(kappa * tot[s] / avg_k, 1) for s in range(S)}
    free = sorted(obs)
    return dict(obs=obs, prio=prio, budget=budget, S=S, N=N, H=H, K=K, seed=seed,
                dur=dur, energy=energy), Problem(obs, prio, set(), budget, set(), free, set(), False)


def make_alert(inst, plan, rng, T, lead, freeze=5, n_urgent=1, k_urgent=3, urgent_prio=20, urgent_windows=None):
    """Build the post-alert problem.  `plan` is the previous (static) plan.
    T: alert time; freeze: observations starting before T+freeze are fixed;
    lead: deadline = T + lead; urgent windows must start >= T+freeze and end <= deadline."""
    obs = dict(inst["obs"])
    prio = dict(inst["prio"])
    S = inst["S"]
    ft, D = T + freeze, T + lead
    frozen = {i for i in plan if obs[i].start < ft}
    covered = {obs[i].target for i in frozen}
    budget = {s: inst["budget"][s] - sum(obs[i].e for i in frozen if obs[i].sat == s) for s in range(S)}
    nid = max(obs) + 1
    urgent = set()
    t0 = max(prio) + 1
    if urgent_windows is not None:           # real windows: list of (sat, start, end, energy), one urgent target
        prio[t0] = urgent_prio
        urgent.add(t0)
        for (s, st, en, e) in urgent_windows:
            if st >= ft and en <= D:
                obs[nid] = Obs(nid, s, t0, st, en, e)
                nid += 1
        n_urgent = 0
    for u in range(n_urgent):
        t = t0 + u
        prio[t] = urgent_prio
        urgent.add(t)
        for s in rng.sample(range(S), min(k_urgent, S)):
            d = rng.randint(*inst["dur"])
            if ft + d > D:
                continue
            st = rng.randint(ft, D - d)
            obs[nid] = Obs(nid, s, t, st, st + d, rng.randint(*inst["energy"]))
            nid += 1
    # free candidates: routine ones starting after the freeze, plus urgent windows
    fro = [obs[i] for i in frozen]
    free = []
    for i, o in obs.items():
        if o.target in covered or i in frozen:
            continue
        if o.target not in urgent and o.start < ft:
            continue
        if o.e > budget[o.sat] or any(overlap(o, f) for f in fro):
            continue
        free.append(i)
    x0 = {i for i in plan if i in set(free)}
    return Problem(obs, prio, urgent, budget, frozen, sorted(free), x0, True)
