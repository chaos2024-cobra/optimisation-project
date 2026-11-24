"""Rebuild data/tle_snapshot.tle and data/satellites.csv from the supplied tle_elements.csv.

The original tle_snapshot.tle was not available, so TLE lines are re-encoded from the parsed elements
(inclination, RAAN, eccentricity, arg. of perigee, mean anomaly, mean motion, B*, epoch).  SGP4 does not use
the derivatives of mean motion, the element-set number or the revolution number, so these are set to 0/dummy.
If you have the original snapshot, put it in data/tle_snapshot.tle and skip this script."""
import csv
from datetime import datetime, timezone

IDS = {39084: ("landsat8", "OLI/TIRS", 185, "USGS Landsat 8"),
       40697: ("sentinel2a", "MSI", 290, "Sentinel-2 MSI"),
       41877: ("resourcesat2a", "AWiFS", 740, "ISRO PSLV-C36 (AWiFS swath; LISS-3 141 km, LISS-4 70 km)"),
       42063: ("sentinel2b", "MSI", 290, "Sentinel-2 MSI"),
       49260: ("landsat9", "OLI-2/TIRS-2", 185, "USGS Landsat 8/9")}


def checksum(line):
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line) % 10


def tle_exp(s):                      # " 60834-4" / "-12019-4" -> 8-char TLE field
    s = s.strip()
    sign = "-" if s.startswith("-") else " "
    return f"{sign}{s.lstrip('+-').strip():>7}"[:8]


rows = list(csv.DictReader(open("data/tle_elements.csv")))
out = []
for r in rows:
    n = int(r["norad_id"]); ep = datetime.fromisoformat(r["tle_epoch_utc"].replace("Z", "+00:00"))
    doy = (ep - datetime(ep.year, 1, 1, tzinfo=timezone.utc)).total_seconds() / 86400 + 1
    epoch = f"{ep.year % 100:02d}{doy:012.8f}"
    l1 = f"1 {n:05d}U {r['international_designator']:<8} {epoch}  .00000000  00000-0 {tle_exp(r['bstar_drag_term'])} 0  999"
    ecc = f"{round(float(r['eccentricity']) * 1e7):07d}"
    l2 = (f"2 {n:05d} {float(r['inclination_deg']):8.4f} {float(r['raan_deg']):8.4f} {ecc} "
          f"{float(r['argument_of_perigee_deg']):8.4f} {float(r['mean_anomaly_deg']):8.4f} "
          f"{float(r['mean_motion_rev_per_day']):11.8f}00001")
    l1 += str(checksum(l1)); l2 += str(checksum(l2))
    assert len(l1) == 69 and len(l2) == 69, (len(l1), len(l2))
    out.append(f"{r['satellite_name']}\n{l1}\n{l2}\n")
open("data/tle_snapshot.tle", "w", newline="\n").write("".join(out))

with open("data/satellites.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["satellite_id", "satellite_name", "norad_id", "instrument", "nominal_swath_km", "swath_reference", "notes"])
    for r in rows:
        sid, inst, sw, ref = IDS[int(r["norad_id"])]
        w.writerow([sid, r["satellite_name"], r["norad_id"], inst, sw, ref, "swath is metadata only"])
print("wrote data/tle_snapshot.tle and data/satellites.csv")
