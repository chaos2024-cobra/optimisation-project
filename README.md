# Satellite Observation Scheduling with Urgent Replanning

**Team name:** Astra

| Member | ID |
| --- | --- |
| Naksh Sharma | BA2025023 |
| R Krish | BA2025035 |
| Arjun Kesav S | BA2025005 |

## Description

Given an issued satellite observation schedule and a newly arriving urgent
imaging request, the program selects a feasible pass before the deadline while
preserving as many routine observations as possible. It compares three
approaches (greedy insertion, restricted replanning, and full-horizon MILP) on
a bundled IAEOSSP benchmark slice. See `Project_Report.pdf` for the model,
validation protocol, results and limitations.

## Libraries used

- Python 3.9+
- SciPy 1.9+ (MILP solver; also installs NumPy)
- Standard library only otherwise (argparse, csv, dataclasses, itertools, etc.)

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```sh
python replan.py                           # floodplain example
python replan.py --deadline 10             # impossible-deadline case
python validate.py --demo T400_S3_G1_H1    # dataset example
python validate.py --output validation.csv # full validation run
python -m unittest -v                      # tests
```
