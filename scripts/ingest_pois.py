#!/usr/bin/env python3
"""Ingest OpenStreetMap POIs via Overpass API — BRIEF §5.3.

Categories are exactly the brief's:
  grocery:   shop=supermarket | shop=convenience
  health:    amenity=clinic | amenity=hospital | amenity=pharmacy
  library:   amenity=library
  education: amenity=school | amenity=university | amenity=college
Madison bounding box (S,W,N,E): 42.99,-89.55,43.18,-89.25.
Unnamed POIs are kept; the UI displays the category label for them.

Usage:
  python scripts/ingest_pois.py --dry-run [--out data/pois.json]
  python scripts/ingest_pois.py            # DB load (DATABASE_URL)
Idempotent: DB load deletes and reloads `pois`, appends a `datasets` row.
On Overpass failure the main endpoint is retried once (in common.fetch_bytes);
then the kumi.systems Overpass mirror is tried once, and which endpoint
served the data is recorded. If both fail, exact errors are logged, exit 1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import connect_db, fetch_json, write_json  # noqa: E402

BBOX = "42.99,-89.55,43.18,-89.25"
ENDPOINTS = [os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter"),
             "https://overpass.kumi.systems/api/interpreter"]
QUERIES = {
    "grocery": 'nwr["shop"~"^(supermarket|convenience)$"]',
    "health": 'nwr["amenity"~"^(clinic|hospital|pharmacy)$"]',
    "library": 'nwr["amenity"="library"]',
    "education": 'nwr["amenity"~"^(school|university|college)$"]',
}


def query_category(category: str, selector: str) -> tuple[list[dict], str]:
    ql = f"[out:json][timeout:120][bbox:{BBOX}];{selector};out center;"
    body = urllib.parse.urlencode({"data": ql}).encode()
    last_err = None
    for endpoint in ENDPOINTS:
        try:
            data = fetch_json(endpoint, data=body, timeout=110)
            pois = []
            for el in data.get("elements", []):
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lon = el.get("lon") or (el.get("center") or {}).get("lon")
                if lat is None or lon is None:
                    continue
                pois.append({"poi_id": f"osm-{el['type']}-{el['id']}",
                             "name": (el.get("tags") or {}).get("name"),
                             "category": category, "lat": float(lat), "lon": float(lon)})
            return pois, endpoint
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[overpass] {category} via {endpoint} failed: {exc!r}", file=sys.stderr)
    raise RuntimeError(f"Overpass failed for {category}: {last_err!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    try:
        all_pois: dict[str, dict] = {}
        endpoints_used = set()
        for category, selector in QUERIES.items():
            pois, endpoint = query_category(category, selector)
            endpoints_used.add(endpoint)
            for p in pois:  # an element matching two selectors keeps its first category
                all_pois.setdefault(p["poi_id"], p)
            print(f"[overpass] {category}: {len(pois)} elements via {endpoint}")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: POI ingest failed: {exc!r}", file=sys.stderr)
        return 1
    pois = sorted(all_pois.values(), key=lambda p: p["poi_id"])
    counts = dict(Counter(p["category"] for p in pois))
    counts["total"] = len(pois)
    payload = {"source": "osm", "vintage": f"OSM extract {date.today().isoformat()}",
               "endpoints": sorted(endpoints_used), "counts": counts, "pois": pois}
    print(f"[pois] counts={counts}")
    if args.out:
        write_json(args.out, payload)
    if not args.dry_run:
        try:
            conn = connect_db()
            with conn, conn.cursor() as cur:
                cur.execute("delete from pois")
                cur.executemany(
                    "insert into pois(poi_id, name, category, geom) values (%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
                    [(p["poi_id"], p["name"], p["category"], p["lon"], p["lat"]) for p in pois])
                cur.execute("insert into datasets(source, vintage, row_counts) values (%s,%s,%s)",
                            ("osm", payload["vintage"], json.dumps(counts)))
            conn.close()
            print(f"[db] loaded POIs: {counts}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: POI DB load failed: {exc!r}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
