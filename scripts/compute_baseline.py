#!/usr/bin/env python3
"""Compute baseline Access Scores with the ONE scoring implementation
(api/scoring.py) — BRIEF §6/§11 Phase 1.

DB mode (default, needs DATABASE_URL): loads tracts/stops/routes/POIs from
Postgres, writes tract_access, and prints the Phase 1 spot check (campus-area
tract vs far-west tract, Education score).

JSON mode (--use-json-dir data): computes the baseline from the dry-run JSON
files (data/gtfs.json, data/census.json, data/pois.json) and writes the merged
demo snapshot to data/snapshot.json. This is the ONLY way the API's demo mode
gets data — always from real ingested data, never invented.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.scoring import AccessModel, Poi, Stop, Tract  # noqa: E402

UW_CAMPUS = (43.0766, -89.4125)   # approx. UW–Madison campus, for the spot check
FAR_WEST = (43.045, -89.540)      # approx. far-west Madison, for the spot check


def model_from_json(d: Path) -> tuple[AccessModel, dict]:
    gtfs = json.loads((d / "gtfs.json").read_text())
    census = json.loads((d / "census.json").read_text())
    pois = json.loads((d / "pois.json").read_text())
    stops = {s["stop_id"]: Stop(s["stop_id"], s["name"], s["lat"], s["lon"]) for s in gtfs["stops"]}
    model = AccessModel(
        stops=stops,
        route_stops={k: set(v) for k, v in gtfs["route_stops"].items()},
        pois=[Poi(p["poi_id"], p["name"], p["category"], p["lat"], p["lon"]) for p in pois["pois"]],
        tracts=[Tract(t["geoid"], t["name"], t["lat"], t["lon"], t["population"],
                      t["median_income"], t["zero_vehicle_pct"]) for t in census["tracts"]],
    )
    return model, {"gtfs": gtfs, "census": census, "pois": pois}


def spot_check(model: AccessModel, scores: dict) -> None:
    def nearest(lat, lon):
        return min(model.tracts.values(),
                   key=lambda t: (t.lat - lat) ** 2 + (t.lon - lon) ** 2)
    campus, west = nearest(*UW_CAMPUS), nearest(*FAR_WEST)
    print(f"[spot-check] campus-area tract {campus.geoid} ({campus.name}): "
          f"education={scores[campus.geoid]['score_education']}, access={scores[campus.geoid]['access_score']}")
    print(f"[spot-check] far-west tract {west.geoid} ({west.name}): "
          f"education={scores[west.geoid]['score_education']}, access={scores[west.geoid]['access_score']}")
    if scores[campus.geoid]["score_education"] <= scores[west.geoid]["score_education"]:
        print("[spot-check] NOTE: campus tract did not outscore far-west on Education — "
              "record this honestly in NOTES.md (proxy-model limits or data vintage).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-json-dir", type=Path, help="compute from dry-run JSON in this dir and write <dir>/snapshot.json")
    args = ap.parse_args()

    if args.use_json_dir:
        d = args.use_json_dir
        try:
            model, raw = model_from_json(d)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: cannot build model from JSON in {d}: {exc!r}", file=sys.stderr)
            return 1
        scores = model.compute_all()
        assert all(0 <= s["access_score"] <= 100 for s in scores.values())
        spot_check(model, scores)
        snapshot = {
            "meta": {"datasets": [
                {"source": "madison_gtfs", "vintage": raw["gtfs"]["vintage"], "row_counts": raw["gtfs"]["counts"]},
                {"source": "acs", "vintage": raw["census"]["vintage"], "row_counts": raw["census"]["counts"]},
                {"source": "osm", "vintage": raw["pois"]["vintage"], "row_counts": raw["pois"]["counts"]},
            ]},
            "tracts": [{**{k: t[k] for k in ("geoid", "name", "population", "median_income",
                                             "zero_vehicle_pct", "lat", "lon", "geometry")},
                        "access": scores[t["geoid"]]} for t in raw["census"]["tracts"]],
            "stops": raw["gtfs"]["stops"],
            "routes": [{**r, "stop_count": len(raw["gtfs"]["route_stops"].get(r["route_id"], [])),
                        "shape": raw["gtfs"]["route_shapes"].get(r["route_id"])}
                       for r in raw["gtfs"]["routes"]],
            "route_stops": raw["gtfs"]["route_stops"],
            "pois": raw["pois"]["pois"],
        }
        out = d / "snapshot.json"
        out.write_text(json.dumps(snapshot))
        print(f"[snapshot] wrote {out} ({out.stat().st_size:,} bytes); "
              f"tracts={len(scores)} mean_access={sum(s['access_score'] for s in scores.values()) / max(len(scores),1):.1f}")
        return 0

    # DB mode
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import connect_db  # noqa: E402
    try:
        conn = connect_db()
        with conn.cursor() as cur:
            cur.execute("select stop_id, name, ST_Y(geom::geometry), ST_X(geom::geometry) from stops")
            stops = {r[0]: Stop(r[0], r[1], r[2], r[3]) for r in cur.fetchall()}
            cur.execute("select route_id, stop_id from route_stops")
            route_stops: dict[str, set[str]] = {}
            for rid, sid in cur.fetchall():
                route_stops.setdefault(rid, set()).add(sid)
            cur.execute("select poi_id, name, category, ST_Y(geom::geometry), ST_X(geom::geometry) from pois")
            pois = [Poi(*r) for r in cur.fetchall()]
            cur.execute("""select geoid, name, ST_Y(centroid::geometry), ST_X(centroid::geometry),
                                  population, median_income, zero_vehicle_pct from tracts""")
            tracts = [Tract(r[0], r[1], r[2], r[3], r[4], r[5],
                            float(r[6]) if r[6] is not None else None) for r in cur.fetchall()]
        model = AccessModel(stops, route_stops, pois, tracts)
        scores = model.compute_all()
        assert all(0 <= s["access_score"] <= 100 for s in scores.values())
        with conn, conn.cursor() as cur:
            cur.execute("delete from tract_access")
            cur.executemany(
                """insert into tract_access(geoid, score_grocery, score_health, score_library,
                                            score_education, access_score)
                   values (%s,%s,%s,%s,%s,%s)""",
                [(g, s["score_grocery"], s["score_health"], s["score_library"],
                  s["score_education"], s["access_score"]) for g, s in scores.items()])
        conn.close()
        spot_check(model, scores)
        print(f"[db] baseline written for {len(scores)} tracts")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: baseline (DB mode) failed: {exc!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
