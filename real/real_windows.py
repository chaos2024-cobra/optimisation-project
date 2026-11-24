#!/usr/bin/env python3
"""Generate real-orbit satellite visibility windows over selected Indian sites.

Orbit propagation is performed by Skyfield's SGP4 implementation using the
included CelesTrak TLE snapshot (or a refreshed CelesTrak Earth-resources set).
The output represents geometric visibility passes, not confirmed image captures.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import numpy as np
    from skyfield.api import EarthSatellite, load, wgs84
except ImportError as exc:  # keep --help usable before dependencies are installed
    np = None  # type: ignore[assignment]
    EarthSatellite = None  # type: ignore[assignment,misc]
    load = None  # type: ignore[assignment]
    wgs84 = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TLE_FILE = DATA / "tle_snapshot.tle"
LOCATIONS_FILE = DATA / "locations.csv"
SATELLITES_FILE = DATA / "satellites.csv"

CELESTRAK_RESOURCE_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=TLE"
)
SELECTED_NORAD_IDS = {39084, 40697, 41877, 42063, 49260}
TLE_CAPTURE_UTC = "2026-11-23T08:13:31Z"


@dataclass(frozen=True)
class Site:
    location_id: str
    location_name: str
    region: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float


@dataclass(frozen=True)
class SatelliteSpec:
    satellite_id: str
    satellite_name: str
    norad_id: int
    instrument: str
    nominal_swath_km: float
    swath_reference: str
    notes: str


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_sites(path: Path = LOCATIONS_FILE) -> list[Site]:
    return [
        Site(
            location_id=row["location_id"].strip(),
            location_name=row["location_name"].strip(),
            region=row["region"].strip(),
            latitude_deg=float(row["latitude_deg"]),
            longitude_deg=float(row["longitude_deg"]),
            elevation_m=float(row["elevation_m"]),
        )
        for row in load_csv_rows(path)
    ]


def load_satellite_specs(path: Path = SATELLITES_FILE) -> list[SatelliteSpec]:
    return [
        SatelliteSpec(
            satellite_id=row["satellite_id"].strip(),
            satellite_name=row["satellite_name"].strip(),
            norad_id=int(row["norad_id"]),
            instrument=row["instrument"].strip(),
            nominal_swath_km=float(row["nominal_swath_km"]),
            swath_reference=row["swath_reference"].strip(),
            notes=row["notes"].strip(),
        )
        for row in load_csv_rows(path)
    ]


def parse_three_line_tles(text: str) -> dict[int, tuple[str, str, str]]:
    """Parse common CelesTrak 3-line TLE text into NORAD-id keyed records."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    records: dict[int, tuple[str, str, str]] = {}
    i = 0
    while i < len(lines):
        if lines[i].startswith("1 "):
            # Some sources omit the title line; tolerate that as well.
            name = "UNKNOWN"
            line1 = lines[i]
            if i + 1 >= len(lines) or not lines[i + 1].startswith("2 "):
                raise ValueError(f"Malformed TLE near line: {line1}")
            line2 = lines[i + 1]
            i += 2
        else:
            if i + 2 >= len(lines):
                raise ValueError(f"Incomplete TLE record beginning with: {lines[i]}")
            name, line1, line2 = lines[i], lines[i + 1], lines[i + 2]
            if not line1.startswith("1 ") or not line2.startswith("2 "):
                raise ValueError(f"Malformed TLE record for {name!r}")
            i += 3
        norad_id = int(line1[2:7])
        if int(line2[2:7]) != norad_id:
            raise ValueError(f"NORAD id mismatch in TLE for {norad_id}")
        records[norad_id] = (name, line1, line2)
    return records


def write_selected_tles(records: dict[int, tuple[str, str, str]], path: Path) -> None:
    missing = sorted(SELECTED_NORAD_IDS - set(records))
    if missing:
        raise RuntimeError(f"CelesTrak response did not include NORAD IDs: {missing}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the manifest ordering for deterministic file diffs.
    ordered_ids = [39084, 40697, 41877, 42063, 49260]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for norad_id in ordered_ids:
            name, line1, line2 = records[norad_id]
            handle.write(f"{name}\n{line1}\n{line2}\n")


def refresh_tles(path: Path = TLE_FILE) -> None:
    request = urllib.request.Request(
        CELESTRAK_RESOURCE_URL,
        headers={"User-Agent": "India-Earth-Observation-Access-Dataset/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
    records = parse_three_line_tles(text)
    write_selected_tles(records, path)
    print(f"Refreshed selected TLEs from CelesTrak into {path}")


def load_satellites(tle_path: Path, ts: Any) -> dict[int, Any]:
    records = parse_three_line_tles(tle_path.read_text(encoding="utf-8"))
    missing = sorted(SELECTED_NORAD_IDS - set(records))
    if missing:
        raise RuntimeError(f"TLE file is missing selected NORAD IDs: {missing}")
    satellites: dict[int, Any] = {}
    for norad_id in sorted(SELECTED_NORAD_IDS):
        name, line1, line2 = records[norad_id]
        satellites[norad_id] = EarthSatellite(line1, line2, name, ts)
    return satellites


def interpolate_crossing(
    t0: datetime, t1: datetime, e0: float, e1: float, threshold: float
) -> datetime:
    """Linearly interpolate the threshold crossing between adjacent samples."""
    if e1 == e0:
        return t1
    fraction = (threshold - e0) / (e1 - e0)
    fraction = min(1.0, max(0.0, fraction))
    return t0 + (t1 - t0) * fraction


def extract_windows(
    datetimes: list[datetime],
    elevation_deg: Any,
    azimuth_deg: Any,
    range_km: Any,
    threshold_deg: float,
    site: Site,
    spec: SatelliteSpec,
    tle_epoch_utc: str,
    sample_step_s: int,
) -> list[dict[str, Any]]:
    mask = elevation_deg >= threshold_deg
    windows: list[dict[str, Any]] = []
    n = len(datetimes)
    i = 0
    while i < n:
        if not bool(mask[i]):
            i += 1
            continue
        first = i
        while i + 1 < n and bool(mask[i + 1]):
            i += 1
        last = i

        truncated_start = first == 0
        truncated_end = last == n - 1
        if truncated_start:
            aos = datetimes[first]
        else:
            aos = interpolate_crossing(
                datetimes[first - 1], datetimes[first],
                float(elevation_deg[first - 1]), float(elevation_deg[first]),
                threshold_deg,
            )
        if truncated_end:
            los = datetimes[last]
        else:
            los = interpolate_crossing(
                datetimes[last], datetimes[last + 1],
                float(elevation_deg[last]), float(elevation_deg[last + 1]),
                threshold_deg,
            )

        local_peak_index = first + int(np.argmax(elevation_deg[first:last + 1]))
        windows.append({
            "window_id": f"{spec.norad_id}-{site.location_id}-{len(windows) + 1:03d}",
            "satellite_id": spec.satellite_id,
            "satellite_name": spec.satellite_name,
            "norad_id": spec.norad_id,
            "instrument": spec.instrument,
            "location_id": site.location_id,
            "location_name": site.location_name,
            "region": site.region,
            "latitude_deg": site.latitude_deg,
            "longitude_deg": site.longitude_deg,
            "aos_utc": iso_utc(aos),
            "los_utc": iso_utc(los),
            "duration_s": round((los - aos).total_seconds(), 1),
            "tca_utc": iso_utc(datetimes[local_peak_index]),
            "max_elevation_deg": round(float(elevation_deg[local_peak_index]), 3),
            "azimuth_at_tca_deg": round(float(azimuth_deg[local_peak_index]) % 360.0, 3),
            "range_at_tca_km": round(float(range_km[local_peak_index]), 3),
            "min_elevation_deg": threshold_deg,
            "nominal_swath_km": spec.nominal_swath_km,
            "swath_is_filter": False,
            "access_type": "geometric_visibility_pass",
            "truncated_at_start": truncated_start,
            "truncated_at_end": truncated_end,
            "tle_epoch_utc": tle_epoch_utc,
            "sample_step_s": sample_step_s,
        })
        i += 1
    return windows


def generate_windows(
    start: datetime,
    days: float,
    min_elevation_deg: float,
    sample_step_s: int,
    sites: list[Site],
    specs: list[SatelliteSpec],
    tle_path: Path,
) -> list[dict[str, Any]]:
    if _IMPORT_ERROR is not None:
        raise RuntimeError(
            "Missing runtime dependency. Install with: python -m pip install -r requirements.txt"
        ) from _IMPORT_ERROR
    if days <= 0 or sample_step_s <= 0:
        raise ValueError("days and sample_step_s must both be positive")
    if not (-5.0 <= min_elevation_deg <= 90.0):
        raise ValueError("min_elevation_deg must be between -5 and 90")

    end = start + timedelta(days=days)
    ts = load.timescale(builtin=True)
    satellites = load_satellites(tle_path, ts)
    spec_by_id = {spec.norad_id: spec for spec in specs}
    satellites = {norad_id: sat for norad_id, sat in satellites.items() if norad_id in spec_by_id}
    results: list[dict[str, Any]] = []

    # Use a shared time grid; each satellite/site pair is vectorized by Skyfield.
    sample_count = int(math.ceil((end - start).total_seconds() / sample_step_s))
    datetimes = [
        start + timedelta(seconds=min(i * sample_step_s, (end - start).total_seconds()))
        for i in range(sample_count + 1)
    ]
    times = ts.from_datetimes(datetimes)

    for norad_id, satellite in satellites.items():
        spec = spec_by_id[norad_id]
        tle_epoch_utc = iso_utc(satellite.epoch.utc_datetime())
        for site in sites:
            observer = wgs84.latlon(
                latitude_degrees=site.latitude_deg,
                longitude_degrees=site.longitude_deg,
                elevation_m=site.elevation_m,
            )
            topocentric = (satellite - observer).at(times)
            alt, az, distance = topocentric.altaz()
            results.extend(extract_windows(
                datetimes=datetimes,
                elevation_deg=alt.degrees,
                azimuth_deg=az.degrees,
                range_km=distance.km,
                threshold_deg=min_elevation_deg,
                site=site,
                spec=spec,
                tle_epoch_utc=tle_epoch_utc,
                sample_step_s=sample_step_s,
            ))
    results.sort(key=lambda row: (row["aos_utc"], row["satellite_id"], row["location_id"]))
    return results


def write_outputs(
    rows: list[dict[str, Any]],
    csv_path: Path,
    start: datetime,
    days: float,
    min_elevation_deg: float,
    sample_step_s: int,
    sites: list[Site],
    specs: list[SatelliteSpec],
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = csv_path.with_suffix(".json")
    manifest_path = csv_path.with_name("manifest.json")
    fieldnames = list(rows[0].keys()) if rows else [
        "window_id", "satellite_id", "satellite_name", "norad_id", "instrument",
        "location_id", "location_name", "region", "latitude_deg", "longitude_deg",
        "aos_utc", "los_utc", "duration_s", "tca_utc", "max_elevation_deg",
        "azimuth_at_tca_deg", "range_at_tca_km", "min_elevation_deg",
        "nominal_swath_km", "swath_is_filter", "access_type",
        "truncated_at_start", "truncated_at_end", "tle_epoch_utc", "sample_step_s",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    manifest = {
        "dataset_name": "India Earth-observation satellite visibility windows",
        "generated_at_utc": iso_utc(datetime.now(timezone.utc)),
        "window_start_utc": iso_utc(start),
        "window_end_utc": iso_utc(start + timedelta(days=days)),
        "horizon_days": days,
        "min_elevation_deg": min_elevation_deg,
        "sample_step_s": sample_step_s,
        "propagator": "Skyfield EarthSatellite (SGP4)",
        "tle_source": "CelesTrak GP Earth Resources group",
        "tle_snapshot_capture_utc": TLE_CAPTURE_UTC,
        "satellite_count": len(specs),
        "location_count": len(sites),
        "window_count": len(rows),
        "satellites": [asdict(spec) for spec in specs],
        "locations": [asdict(site) for site in sites],
        "interpretation": (
            "Rows are geometric satellite visibility passes above the selected minimum "
            "elevation at representative city-centre coordinates. They are not confirmed "
            "image acquisitions, tasking opportunities, or cloud-free observations."
        ),
        "swath_note": (
            "Nominal sensor swath widths are included as metadata only. The current pass "
            "filter is elevation-only; no sensor-specific off-nadir steering, footprint, "
            "sunlight, cloud, acquisition-plan, or downlink constraints are applied."
        ),
        "synthetic_fields_excluded": ["priority", "energy_cost", "energy_budget", "data_budget"],
        "files": [csv_path.name, json_path.name, manifest_path.name],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=None, help="UTC/ISO start time; default: now")
    parser.add_argument("--days", type=float, default=7.0, help="Propagation horizon in days (default: 7)")
    parser.add_argument("--min-elevation", type=float, default=10.0, help="Minimum topocentric elevation in degrees (default: 10)")
    parser.add_argument("--step-seconds", type=int, default=30, help="Sampling step in seconds (default: 30)")
    parser.add_argument("--out", default=str(DATA / "real_windows.csv"), help="CSV output path")
    parser.add_argument("--refresh-tle", action="store_true", help="Fetch a fresh CelesTrak Earth Resources TLE set before propagation")
    parser.add_argument("--sites", default=None, help="Optional comma-separated location_id allow-list")
    parser.add_argument("--satellites", default=None, help="Optional comma-separated NORAD ID allow-list")
    args = parser.parse_args()

    if args.refresh_tle:
        refresh_tles(TLE_FILE)

    sites = load_sites()
    specs = load_satellite_specs()
    if args.sites:
        allowed = {item.strip() for item in args.sites.split(",") if item.strip()}
        sites = [site for site in sites if site.location_id in allowed]
        unknown = allowed - {site.location_id for site in sites}
        if unknown:
            parser.error(f"Unknown location_id(s): {sorted(unknown)}")
    if args.satellites:
        allowed_ids = {int(item.strip()) for item in args.satellites.split(",") if item.strip()}
        specs = [spec for spec in specs if spec.norad_id in allowed_ids]
        if allowed_ids - {spec.norad_id for spec in specs}:
            parser.error(f"Unknown NORAD ID(s): {sorted(allowed_ids - {spec.norad_id for spec in specs})}")

    start = parse_utc(args.start) if args.start else datetime.now(timezone.utc).replace(microsecond=0)
    rows = generate_windows(
        start=start,
        days=args.days,
        min_elevation_deg=args.min_elevation,
        sample_step_s=args.step_seconds,
        sites=sites,
        specs=specs,
        tle_path=TLE_FILE,
    )
    out_path = Path(args.out).expanduser().resolve()
    write_outputs(rows, out_path, start, args.days, args.min_elevation, args.step_seconds, sites, specs)
    print(f"Created {len(rows)} visibility windows")
    print(f"CSV: {out_path}")
    print(f"JSON: {out_path.with_suffix('.json')}")
    print(f"Manifest: {out_path.with_name('manifest.json')}")
    if not rows:
        print("No passes met the selected elevation threshold in this horizon.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
