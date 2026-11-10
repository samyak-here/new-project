#!/usr/bin/env python3
"""Ingest Madison Metro GTFS (static) — BRIEF §5.1.

Idempotent: a DB load deletes and reloads routes/stops/route_stops and adds a
`datasets` row with the real counts. Re-runnable.

Usage:
  python scripts/ingest_gtfs.py --dry-run [--out data/gtfs.json]   # parse + validate, no DB
  python scripts/ingest_gtfs.py                                    # load into Postgres (DATABASE_URL)
  python scripts/ingest_gtfs.py --file /path/mmt_gtfs.zip          # parse a local copy

Never fabricates data: if the feed cannot be downloaded after one retry, the
exact error is printed and the script exits non-zero.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, connect_db, fetch_bytes, write_json  # noqa: E402

GTFS_URL = os.environ.get("GTFS_URL", "https://transitdata.cityofmadison.com/GTFS/mmt_gtfs.zip")


def _rows(zf: zipfile.ZipFile, name: str):
    if name not in zf.namelist():
        return
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        yield from csv.DictReader(text)


def parse_gtfs(raw: bytes) -> dict:
    zf = zipfile.ZipFile(io.BytesIO(raw))
    routes = []
    for r in _rows(zf, "routes.txt"):
        routes.append({
            "route_id": r["route_id"],
            "short_name": (r.get("route_short_name") or "").strip(),
            "long_name": (r.get("route_long_name") or "").strip(),
            "color": (r.get("route_color") or "").strip() or None,
        })
    stops = []
    for s in _rows(zf, "stops.txt"):
        try:
            lat, lon = float(s["stop_lat"]), float(s["stop_lon"])
        except (TypeError, ValueError, KeyError):
            continue
        stops.append({"stop_id": s["stop_id"], "name": (s.get("stop_name") or "").strip(),
                      "lat": lat, "lon": lon})
    stop_ids = {s["stop_id"] for s in stops}
    route_ids = {r["route_id"] for r in routes}

    trip_route: dict[str, str] = {}
    trip_shape: dict[str, str] = {}
    for t in _rows(zf, "trips.txt"):
        trip_route[t["trip_id"]] = t["route_id"]
        if t.get("shape_id"):
            trip_shape[t["trip_id"]] = t["shape_id"]

    route_stops: dict[str, set[str]] = defaultdict(set)
    for st in _rows(zf, "stop_times.txt"):
        route_id = trip_route.get(st["trip_id"])
        if route_id in route_ids and st["stop_id"] in stop_ids:
            route_stops[route_id].add(st["stop_id"])

    # Route shapes: per route, the shape (from its trips) with the most points.
    shapes: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for sh in _rows(zf, "shapes.txt"):
        try:
            shapes[sh["shape_id"]].append(
                (int(sh["shape_pt_sequence"]), float(sh["shape_pt_lat"]), float(sh["shape_pt_lon"])))
        except (TypeError, ValueError, KeyError):
            continue
    route_shapes: dict[str, list[list[float]]] = {}
    shapes_by_route: dict[str, list[str]] = defaultdict(set)
    for trip_id, shape_id in trip_shape.items():
        if trip_route.get(trip_id):
            shapes_by_route[trip_route[trip_id]].add(shape_id)
    for route_id, shape_ids in shapes_by_route.items():
        best = max(shape_ids, key=lambda sid: len(shapes.get(sid, [])))
        pts = sorted(shapes.get(best, []))
        if pts:
            route_shapes[route_id] = [[lon, lat] for _seq, lat, lon in pts]

    vintage = None
    for fi in _rows(zf, "feed_info.txt"):
        vintage = fi.get("feed_version") or fi.get("feed_start_date")
    if not vintage:
        for cal in _rows(zf, "calendar.txt"):
            vintage = cal.get("start_date")
            break

    counts = {"routes": len(routes), "stops": len(stops),
              "route_stops": sum(len(v) for v in route_stops.values()),
              "shapes": len(route_shapes)}
    assert counts["stops"] > 1000, f"sanity check failed: only {counts['stops']} stops (BRIEF §5 expects >1000)"
    assert counts["routes"] > 20, f"sanity check failed: only {counts['routes']} routes (BRIEF §5 expects >20)"
    return {"source": "madison_gtfs", "vintage": str(vintage) if vintage else None,
            "counts": counts, "routes": routes, "stops": stops,
            "route_stops": {k: sorted(v) for k, v in route_stops.items()},
            "route_shapes": route_shapes}


def load_db(payload: dict) -> None:
    conn = connect_db()
    with conn, conn.cursor() as cur:
        cur.execute("delete from route_stops")
        cur.execute("delete from stops")
        cur.execute("delete from routes")
        cur.executemany(
            "insert into routes(route_id, short_name, long_name, color) values (%s,%s,%s,%s)",
            [(r["route_id"], r["short_name"], r["long_name"], r["color"]) for r in payload["routes"]])
        cur.executemany(
            "insert into stops(stop_id, name, geom) values (%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
            [(s["stop_id"], s["name"], s["lon"], s["lat"]) for s in payload["stops"]])
        cur.executemany(
            "insert into route_stops(route_id, stop_id) values (%s,%s) on conflict do nothing",
            [(rid, sid) for rid, sids in payload["route_stops"].items() for sid in sids])
        cur.execute("insert into datasets(source, vintage, row_counts) values (%s,%s,%s)",
                    ("madison_gtfs", payload["vintage"], json.dumps(payload["counts"])))
    conn.close()
    print(f"[db] loaded GTFS: {payload['counts']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="parse + validate only, no DB")
    ap.add_argument("--out", type=Path, help="also write parsed JSON here")
    ap.add_argument("--file", type=Path, help="parse a local GTFS zip instead of downloading")
    args = ap.parse_args()
    try:
        raw = args.file.read_bytes() if args.file else fetch_bytes(GTFS_URL)
        payload = parse_gtfs(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: GTFS ingest failed: {exc!r} (url={GTFS_URL})", file=sys.stderr)
        return 1
    print(f"[gtfs] vintage={payload['vintage']} counts={payload['counts']}")
    if args.out:
        write_json(args.out, payload)
    if not args.dry_run:
        try:
            load_db(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: GTFS DB load failed: {exc!r}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
