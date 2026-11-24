"""Adapter: real satellite visibility passes (real/data/real_windows.csv) -> scheduling candidates.

Modelling assumptions (all explicit, all tunable):
  * a pass becomes a candidate only if the sensor could point at the site: off-nadir angle at closest approach
    <= max_offnadir (a steerable sensor; Landsat/Sentinel-2 are NOT steerable, so this is a what-if);
  * optical sensors need light: local mean solar time at closest approach in [day_from, day_to] hours;
  * the observation occupies a fixed `slot` minutes centred on closest approach (imaging + settling);
  * energy cost = 1 + 3 * offnadir/max_offnadir, rounded (more slew = more energy);  SYNTHETIC;
  * a routine target is a (site, day) monitoring request; its priority (1-10) is SYNTHETIC and seeded;
  * the per-satellite energy budget is kappa * (total candidate energy / windows per target);  SYNTHETIC.
Time unit: minutes from the start of the window file."""
import csv, math, random
from datetime import datetime, timezone
from model import Obs, Problem

RE = 6371.0
SATS = ["landsat8", "landsat9", "resourcesat2a", "sentinel2a", "sentinel2b"]


def _t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_passes(path="real/data/real_windows.csv", max_offnadir=30.0, day_from=8.0, day_to=16.0):
    rows = list(csv.DictReader(open(path)))
    import json, os
    man = os.path.join(os.path.dirname(path), "manifest.json")
    t0 = _t(json.load(open(man))["window_start_utc"]) if os.path.exists(man) else min(_t(r["aos_utc"]) for r in rows)
    out = []
    for r in rows:
        el = math.radians(float(r["max_elevation_deg"])); rng = float(r["range_at_tca_km"])
        rs = math.sqrt(RE ** 2 + rng ** 2 + 2 * RE * rng * math.sin(el))
        eta = math.degrees(math.asin(RE * math.cos(el) / rs))
        tca = _t(r["tca_utc"])
        lst = (tca.hour + tca.minute / 60 + float(r["longitude_deg"]) / 15) % 24
        if eta > max_offnadir or not (day_from <= lst <= day_to):
            continue
        out.append(dict(site=r["location_id"], sat=SATS.index(r["satellite_id"]), offnadir=eta,
                        tca=(tca - t0).total_seconds() / 60,
                        aos=(_t(r["aos_utc"]) - t0).total_seconds() / 60,
                        los=(_t(r["los_utc"]) - t0).total_seconds() / 60))
    return out, t0


def real_instance(passes, kappa=0.55, slot=5.0, max_offnadir=30.0, seed=0, horizon_days=7):
    rng = random.Random(seed)
    sites = sorted({p["site"] for p in passes})
    obs, prio, tkey, nid = {}, {}, {}, 0
    keys = {}
    for p in sorted(passes, key=lambda p: p["tca"]):
        key = (p["site"], int(p["tca"] // 1440))
        if key not in keys:
            keys[key] = len(keys); prio[keys[key]] = rng.randint(1, 10)
        st = max(p["aos"], p["tca"] - slot / 2); en = min(p["los"], st + slot)
        e = 1 + round(3 * p["offnadir"] / max_offnadir)
        obs[nid] = Obs(nid, p["sat"], keys[key], round(st, 2), round(en, 2), e); nid += 1
    S = len(SATS); N = len(keys)
    tot = {s: sum(o.e for o in obs.values() if o.sat == s) for s in range(S)}
    budget = {s: round(kappa * tot[s] / (len(obs) / N), 1) for s in range(S)}
    inst = dict(obs=obs, prio=prio, budget=budget, S=S, N=N, H=horizon_days * 1440, seed=seed,
                keys=keys, sites=sites, slot=slot, max_offnadir=max_offnadir)
    return inst, Problem(obs, prio, set(), budget, set(), sorted(obs), set(), False)


def urgent_windows_for(inst, passes, site, slot=None):
    slot = slot or inst["slot"]; out = []
    for p in passes:
        if p["site"] != site:
            continue
        st = max(p["aos"], p["tca"] - slot / 2); en = min(p["los"], st + slot)
        out.append((p["sat"], round(st, 2), round(en, 2), 1 + round(3 * p["offnadir"] / inst["max_offnadir"])))
    return out
