#!/usr/bin/env python3
"""Ingest US Census ACS 5-year tracts for Dane County, WI — BRIEF §5.2.

State FIPS 55, county 025. Variables:
  B01003_001E  total population
  B19013_001E  median household income (negative sentinel -> null)
  B25044_001E  total households (tenure by vehicles available)
  B25044_003E  owner-occupied, zero vehicles
  B25044_010E  renter-occupied, zero vehicles
  zero_vehicle_pct = 100 * (003E + 010E) / 001E

Tract geometry + centroids, in order:
  1. Census cartographic boundary KML (GENZ cb_*_55_tract_500k.zip), filtered
     to county 025; centroid = polygon centroid of the largest ring.
  2. TIGERweb REST (layer discovered from the service directory), f=geojson.
If both geometry sources fail, the exact errors are logged and the script
exits non-zero — a tract without a centroid cannot be scored, and inventing
coordinates is forbidden (BRIEF §13).

Usage:
  python scripts/ingest_census.py --dry-run [--out data/census.json]
  python scripts/ingest_census.py            # DB load (DATABASE_URL)
Idempotent: DB load upserts tracts and appends a `datasets` row.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import connect_db, fetch_bytes, fetch_json, write_json  # noqa: E402

CENSUS_BASE = os.environ.get("CENSUS_API_BASE", "https://api.census.gov/data")
STATE, COUNTY = "55", "025"
VARIABLES = "NAME,B01003_001E,B19013_001E,B25044_001E,B25044_003E,B25044_010E"


def fetch_acs_via_census_reporter() -> tuple[str, list[dict]]:
    """Keyless fallback: Census Reporter republishes the same ACS 5-year
    tables. Used only when no CENSUS_API_KEY is configured, because
    api.census.gov now requires a key (verified 2026-11-09: HTTP 302 to
    missing_key.html with header X-DataWebAPI-KeyError: 1)."""
    url = ("https://api.censusreporter.org/1.0/data/show/latest"
           "?table_ids=B01003,B19013,B25044&geo_ids=140%7C05000US55025")
    payload = fetch_json(url)
    release = (payload.get("release") or {}).get("name") or "ACS 5-year (latest via Census Reporter)"
    names = (payload.get("geography") or {}).get("this", {})
    tracts = []
    for full_geoid, tables in (payload.get("data") or {}).items():
        geoid = full_geoid.replace("14000US", "")

        def est(table, var):
            v = ((tables.get(table) or {}).get("estimate") or {}).get(var)
            return int(v) if v is not None else None

        total_hh = est("B25044", "B25044001") or 0
        zero_veh = (est("B25044", "B25044003") or 0) + (est("B25044", "B25044010") or 0)
        income = est("B19013", "B19013001")
        tracts.append({
            "geoid": geoid,
            "name": (names.get(full_geoid) or {}).get("name") or f"Census Tract {geoid[-6:]}",
            "population": est("B01003", "B01003001") or 0,
            "median_income": income if income and income > 0 else None,
            "zero_vehicle_pct": round(100.0 * zero_veh / total_hh, 2) if total_hh else None,
        })
    if not tracts:
        raise RuntimeError(f"Census Reporter returned no tracts: {url}")
    return release, tracts


def fetch_acs() -> tuple[str, list[dict]]:
    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        print("[acs] no CENSUS_API_KEY set; api.census.gov requires one — "
              "using Census Reporter (same ACS tables)", file=sys.stderr)
        return fetch_acs_via_census_reporter()
    last_err = None
    for year in (2024, 2023, 2022):
        url = (f"{CENSUS_BASE}/{year}/acs/acs5?get={VARIABLES}"
               f"&for=tract:*&in=state:{STATE}&in=county:{COUNTY}&key={api_key}")
        try:
            rows = fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[acs] {year} failed: {exc!r}", file=sys.stderr)
            continue
        header, data = rows[0], rows[1:]
        idx = {name: i for i, name in enumerate(header)}
        tracts = []
        for row in data:
            def num(key):
                v = row[idx[key]]
                return int(v) if v not in (None, "") else None
            total_hh = num("B25044_001E") or 0
            zero_veh = (num("B25044_003E") or 0) + (num("B25044_010E") or 0)
            income = num("B19013_001E")
            tracts.append({
                "geoid": f"{STATE}{COUNTY}{row[idx['tract']]}",
                "name": row[idx["NAME"]],
                "population": num("B01003_001E") or 0,
                "median_income": income if income and income > 0 else None,
                "zero_vehicle_pct": round(100.0 * zero_veh / total_hh, 2) if total_hh else None,
            })
        return f"ACS {year} 5-year", tracts
    raise RuntimeError(f"ACS fetch failed for 2024/2023/2022: {last_err!r}")


# --- geometry: cartographic boundary KML -------------------------------------
KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Polygon centroid (shoelace) for a [lon, lat] ring; falls back to mean."""
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a))


def geometry_from_kml(year: int) -> dict[str, dict]:
    url = f"https://www2.census.gov/geo/tiger/GENZ{year}/kml/cb_{year}_55_tract_500k.zip"
    raw = fetch_bytes(url)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    kml_name = next(n for n in zf.namelist() if n.endswith(".kml"))
    root = ET.fromstring(zf.read(kml_name))
    out: dict[str, dict] = {}
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        fields = {sd.get("name"): (sd.text or "") for sd in pm.iter("{http://www.opengis.net/kml/2.2}SimpleData")}
        if fields.get("COUNTYFP") != COUNTY or not fields.get("GEOID"):
            continue
        polygons = []
        for poly in pm.iter("{http://www.opengis.net/kml/2.2}Polygon"):
            coords_el = poly.find(".//kml:coordinates", KML_NS)
            if coords_el is None or not coords_el.text:
                continue
            ring = [[float(c.split(",")[0]), float(c.split(",")[1])]
                    for c in coords_el.text.split()]
            if len(ring) >= 4:
                polygons.append(ring)
        if not polygons:
            continue
        largest = max(polygons, key=lambda r: len(r))
        lon, lat = _ring_centroid(largest)
        geojson = ({"type": "Polygon", "coordinates": [largest]} if len(polygons) == 1
                   else {"type": "MultiPolygon", "coordinates": [[r] for r in polygons]})
        out[fields["GEOID"]] = {"lat": lat, "lon": lon, "geometry": geojson}
    if not out:
        raise RuntimeError(f"KML parsed but no tracts for county {COUNTY}: {url}")
    return out


def geometry_from_tigerweb() -> dict[str, dict]:
    services = [
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer",
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Census2020/MapServer",
    ]
    last_err = None
    for svc in services:
        try:
            directory = fetch_json(f"{svc}?f=json")
            layer_id = None
            for layer in directory.get("layers", []):
                if "tract" in layer.get("name", "").lower():
                    layer_id = layer["id"]
                    break
            if layer_id is None:
                continue
            url = (f"{svc}/{layer_id}/query?where=STATE%3D%27{STATE}%27%20AND%20COUNTY%3D%27{COUNTY}%27"
                   f"&outFields=GEOID&returnGeometry=true&f=geojson&resultRecordCount=500")
            fc = fetch_json(url)
            out = {}
            for feat in fc.get("features", []):
                geoid = feat["properties"].get("GEOID")
                geom = feat.get("geometry")
                if not geoid or not geom:
                    continue
                rings = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
                lon, lat = _ring_centroid(rings)
                out[geoid] = {"lat": lat, "lon": lon, "geometry": geom}
            if out:
                return out
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[tigerweb] {svc} failed: {exc!r}", file=sys.stderr)
    raise RuntimeError(f"TIGERweb geometry failed: {last_err!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    try:
        vintage, tracts = fetch_acs()
        geoms, geom_source = None, None
        last_kml_err = None
        for kml_year in (2024, 2023, 2022):
            try:
                geoms = geometry_from_kml(kml_year)
                geom_source = f"GENZ{kml_year} cartographic KML"
                break
            except Exception as kml_err:  # noqa: BLE001
                last_kml_err = kml_err
                print(f"[geometry] GENZ{kml_year} KML failed: {kml_err!r}", file=sys.stderr)
        if geoms is None:
            print(f"[geometry] all KML years failed (last: {last_kml_err!r}); trying TIGERweb",
                  file=sys.stderr)
            geoms = geometry_from_tigerweb()
            geom_source = "TIGERweb REST"
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Census ingest failed: {exc!r}", file=sys.stderr)
        return 1
    missing = [t["geoid"] for t in tracts if t["geoid"] not in geoms]
    for t in tracts:
        g = geoms.get(t["geoid"])
        if g:
            t.update({"lat": g["lat"], "lon": g["lon"], "geometry": g["geometry"]})
    tracts = [t for t in tracts if "lat" in t]
    payload = {"source": "acs", "vintage": vintage,
               "geometry_source": geom_source,
               "counts": {"tracts": len(tracts), "tracts_missing_geometry": len(missing)},
               "tracts": tracts}
    print(f"[census] vintage={payload['vintage']} geometry={geom_source} counts={payload['counts']}")
    if missing:
        print(f"[census] WARNING: {len(missing)} tracts without geometry were dropped: {missing[:5]}")
    if args.out:
        write_json(args.out, payload)
    if not args.dry_run:
        try:
            conn = connect_db()
            with conn, conn.cursor() as cur:
                for t in tracts:
                    cur.execute(
                        """insert into tracts(geoid, name, population, median_income, zero_vehicle_pct, geom, centroid)
                           values (%s,%s,%s,%s,%s, ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)::geography,
                                   ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)
                           on conflict (geoid) do update set name=excluded.name,
                             population=excluded.population, median_income=excluded.median_income,
                             zero_vehicle_pct=excluded.zero_vehicle_pct, geom=excluded.geom,
                             centroid=excluded.centroid""",
                        (t["geoid"], t["name"], t["population"], t["median_income"],
                         t["zero_vehicle_pct"], json.dumps(t["geometry"]), t["lon"], t["lat"]))
                cur.execute("insert into datasets(source, vintage, row_counts) values (%s,%s,%s)",
                            ("acs", payload["vintage"], json.dumps(payload["counts"])))
            conn.close()
            print(f"[db] loaded Census: {payload['counts']}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: Census DB load failed: {exc!r}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
