#!/usr/bin/env python3
"""Export the API demo snapshot from real dry-run ingest output.

The API's demo mode (DATABASE_URL unset) serves data/snapshot.json ONLY.
This script is the supported way to produce it — it is a thin wrapper around
compute_baseline.py --use-json-dir, which merges data/gtfs.json +
data/census.json + data/pois.json (all produced by the ingest scripts from
the real public sources) and computes baseline Access Scores with
api/scoring.py. If any input is missing, it fails loudly; it never invents
data.

Usage:
  python scripts/ingest_gtfs.py   --dry-run --out data/gtfs.json
  python scripts/ingest_census.py --dry-run --out data/census.json
  python scripts/ingest_pois.py   --dry-run --out data/pois.json
  python scripts/export_snapshot.py [--export-snapshot]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    for name in ("gtfs.json", "census.json", "pois.json"):
        if not (ROOT / "data" / name).exists():
            print(f"ERROR: data/{name} missing — run the ingest scripts first (see docstring).",
                  file=sys.stderr)
            raise SystemExit(1)
    raise SystemExit(subprocess.call(
        [sys.executable, str(ROOT / "scripts" / "compute_baseline.py"),
         "--use-json-dir", str(ROOT / "data")]))
