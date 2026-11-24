# India Earth-observation real-orbit access dataset

This package contains a public TLE snapshot for five Earth-observation satellites, representative Indian flood-risk locations, and a reproducible generator for seven-day satellite visibility windows.

## What is included

- `data/tle_snapshot.tle` — five CelesTrak TLE records captured from the Earth Resources group on **2026-11-23 08:13:31 UTC**.
- `data/tle_elements.csv` — parsed orbital-element columns and TLE epochs for those five records.
- `data/locations.csv` — representative points in the Brahmaputra basin, Ganga basin, Kerala, Chennai, Mumbai, and Bengaluru. Coordinates and elevations are approximate city-centre values, not basin polygons or surveyed ground-control points.
- `data/satellites.csv` — satellite/instrument metadata and nominal swath widths. For Resourcesat-2A, the 740 km value is specifically the AWiFS swath; LISS-3 is 141 km and LISS-4 is 70 km.
- `data/site_satellite_pairs.csv` — all 40 satellite/site combinations (5 satellites × 8 representative sites).
- `data/manifest_inputs.json` — input snapshot metadata and validated record counts.
- `real_windows.py` — Skyfield/SGP4 propagation and pass-window extraction.
- `requirements.txt` and `run_windows.bat` — Windows setup and one-command run.

## Generate the actual windows

From this folder in Windows PowerShell or Command Prompt:

```powershell
python -m pip install -r requirements.txt
python real_windows.py --start 2026-11-23T12:38:00Z --days 7 --min-elevation 10 --step-seconds 30
```

The script creates:

- `data/real_windows.csv`
- `data/real_windows.json`
- `data/manifest.json`

To refresh the orbital elements from CelesTrak first:

```powershell
python real_windows.py --refresh-tle --days 7 --min-elevation 10
```

The refresh makes one request to CelesTrak's public GP Earth Resources group and extracts the five selected NORAD catalog numbers. The included snapshot makes the first run reproducible without a TLE download.

## Satellites

| Satellite | NORAD ID | Payload | Nominal swath metadata |
|---|---:|---|---:|
| Landsat 8 | 39084 | OLI/TIRS | 185 km |
| Sentinel-2A | 40697 | MSI | 290 km |
| Resourcesat-2A | 41877 | AWiFS | 740 km |
| Sentinel-2B | 42063 | MSI | 290 km |
| Landsat 9 | 49260 | OLI-2/TIRS-2 | 185 km |

## Meaning of a window

The generated rows are **geometric visibility passes**: the satellite is above the location's local horizon by at least the selected topocentric elevation (10 degrees by default). AOS/LOS are linearly interpolated between 30-second samples. TCA is the sampled time of maximum elevation within the pass.

The swath widths are carried as metadata, not used to gate the current windows. A visibility pass is not proof that the sensor can or will acquire that point. A sensor-specific observation opportunity would additionally require ground-track/cross-track footprint geometry, steering limits, acquisition plans, daylight/solar-angle checks for optical sensors, cloud screening, and mission scheduling. Keep this distinction in the report.

No priority, energy cost, energy budget, data budget, or observation-success values are inferred from TLEs. Those remain explicitly synthetic model inputs in the optimisation experiments.

## Output fields

The CSV/JSON contain a stable generic observation-window record: `window_id`, satellite and location identifiers, `aos_utc`, `los_utc`, duration, time of maximum elevation, maximum elevation, azimuth, range, elevation threshold, source TLE epoch, sampling interval, and truncation flags. This is intentionally a generic adapter boundary; the project-specific `Obs` constructor was not supplied with this request, so no incompatible constructor signature has been guessed.

## Caveats

- TLEs are time-tagged orbital estimates. Prediction quality degrades with propagation horizon and manoeuvres; record the TLE epoch and refresh for future experiments.
- Site coordinates are city-centre representatives. A basin-scale study should replace these points with a grid or polygon sample.
- The output is not imagery, acquisition history, cloud-free coverage, or proof of a scheduled acquisition.
- The seven-day start/end dates in a run are stored in `manifest.json`; use a fixed `--start` for reproducible experiments.

## Sources

- CelesTrak GP Earth Resources group: <https://celestrak.org/NORAD/elements/table.php?FORMAT=tle&GROUP=resource>
- CelesTrak GP data API documentation: <https://celestrak.org/NORAD/documentation/gp-data-formats.php>
- Sentinel-2 MSI swath specification: <https://s2.pages.eopf.copernicus.eu/msi/s2msi/main/PDFS_ADFS/index.html>
- Landsat 8 mission/swath facts: <https://www.usgs.gov/landsat-missions/landsat-8>
- Resourcesat-2A payload specifications: <https://www.isro.gov.in/media_isro/pdf/Missions/PSLV-C36.pdf>
