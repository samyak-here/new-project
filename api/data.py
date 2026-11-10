"""Data sources for the Isthmus API.

Two real modes, one honest failure mode (BRIEF §13 — never invent data):
  * DbSource       — DATABASE_URL set: reads Postgres/PostGIS, persists
                     simulations to `simulations` + `simulation_impacts`.
  * SnapshotSource — DATABASE_URL unset: serves data/snapshot.json, which is
                     produced ONLY by scripts/export_snapshot.py from real
                     ingest dry-runs. Simulations are computed live with
                     api/scoring.py and held in memory (demo mode).
  * If neither is available, get_default_source() raises DataUnavailable and
    the API answers 503 with instructions — never fabricated data.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .scoring import AccessModel, Poi, Stop, Tract, run_simulation

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "data" / "snapshot.json"

METHOD = {
    "summary": "Access Score is a simplified transit-access proxy, not door-to-door directions.",
    "formula": ("For each census tract (represented by its centroid): a place is reachable if a bus "
                "route serves both a stop within 800 m of the centroid and a stop within 800 m of "
                "the place, or the place is within 800 m on foot. Time proxy = walk at 80 m/min + "
                "ride at 400 m/min (great-circle). Category score = 100 at 15 min or less, falling "
                "linearly to 0 at 45 min; unreachable = 0. Access Score = mean of Grocery, Health, "
                "Library and Education/Campus category scores."),
    "walk_radius_m": 800,
    "categories": ["grocery", "health", "library", "education"],
}


class DataUnavailable(Exception):
    pass


def _tract_label(tract: Tract) -> str:
    if tract.name:
        name = tract.name
        if name.lower().startswith("census tract "):
            name = name[len("Census Tract "):].split(",")[0].strip()
            # Raw 6-digit tract codes: 001102 -> "11.02", 000100 -> "1"
            if name.isdigit() and len(name) == 6:
                whole, frac = int(name[:4]), name[4:]
                name = f"{whole}.{frac}" if frac != "00" else str(whole)
            return "Tract " + name
        return name
    return f"Tract {tract.geoid[-4:]}"


class BaseSource:
    demo_mode = False

    def __init__(self):
        self._model: AccessModel | None = None
        self._baseline: dict | None = None
        self._datasets: list[dict] = []
        self._route_shapes: dict[str, list | None] = {}

    # -- to be provided by subclasses --------------------------------------
    def _load(self):
        raise NotImplementedError

    def _persist_simulation(self, payload: dict) -> str:
        raise NotImplementedError

    def _load_simulation(self, sim_id: str) -> dict | None:
        raise NotImplementedError

    # -- shared behaviour ----------------------------------------------------
    @property
    def model(self) -> AccessModel:
        if self._model is None:
            self._load()
        return self._model

    @property
    def baseline(self) -> dict:
        if self._baseline is None:
            stored = getattr(self, "_stored_baseline", None)
            self._baseline = stored if stored else self.model.compute_all()
        return self._baseline

    def meta(self) -> dict:
        _ = self.model  # ensure datasets are loaded
        return {"datasets": self._datasets, "method": METHOD, "demo_mode": self.demo_mode}

    def tracts_geojson(self) -> dict:
        model, baseline = self.model, self.baseline
        features = []
        for geoid, tract in model.tracts.items():
            scores = baseline[geoid]
            geom = self._tract_geometry(geoid)
            features.append({
                "type": "Feature",
                "geometry": geom or {"type": "Point", "coordinates": [tract.lon, tract.lat]},
                "properties": {
                    "geoid": geoid, "name": _tract_label(tract),
                    "population": tract.population, "median_income": tract.median_income,
                    "zero_vehicle_pct": tract.zero_vehicle_pct,
                    "access_score": scores["access_score"],
                    "score_grocery": scores["score_grocery"], "score_health": scores["score_health"],
                    "score_library": scores["score_library"], "score_education": scores["score_education"],
                },
            })
        return {"type": "FeatureCollection", "features": features}

    def _tract_geometry(self, geoid: str):
        return getattr(self, "_geometries", {}).get(geoid)

    def stops_geojson(self) -> dict:
        model = self.model
        features = []
        for stop in model.stops.values():
            routes = sorted(model.stop_routes.get(stop.stop_id, set()))
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [stop.lon, stop.lat]},
                "properties": {"stop_id": stop.stop_id, "name": stop.name, "routes": routes},
            })
        return {"type": "FeatureCollection", "features": features}

    def routes_payload(self) -> dict:
        model = self.model
        routes, features = [], []
        for route_id in sorted(model.route_stops):
            meta = self._route_meta.get(route_id, {}) if hasattr(self, "_route_meta") else {}
            routes.append({
                "route_id": route_id, "short_name": meta.get("short_name"),
                "long_name": meta.get("long_name"), "color": meta.get("color"),
                "stop_count": len(model.route_stops[route_id]),
            })
            shape = self._route_shapes.get(route_id)
            features.append({
                "type": "Feature",
                "geometry": ({"type": "LineString", "coordinates": shape} if shape else None),
                "properties": {"route_id": route_id, "short_name": meta.get("short_name")},
            })
        return {"routes": routes, "geojson": {"type": "FeatureCollection", "features": features}}

    def pois_geojson(self, category: str | None) -> dict:
        features = []
        for poi in self.model.pois:
            if category and poi.category != category:
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [poi.lon, poi.lat]},
                "properties": {"poi_id": poi.poi_id, "name": poi.name, "category": poi.category},
            })
        return {"type": "FeatureCollection", "features": features}

    def list_routes(self) -> list[dict]:
        return self.routes_payload()["routes"]

    def list_stops(self) -> list[dict]:
        return [{"stop_id": s.stop_id, "name": s.name} for s in self.model.stops.values()]

    # -- simulations ---------------------------------------------------------
    def simulate(self, kind: str, target_id: str, label: str | None) -> dict:
        model = self.model
        if kind == "route" and target_id not in model.route_stops:
            raise KeyError(f"unknown route {target_id!r}")
        if kind == "stop" and target_id not in model.stops:
            raise KeyError(f"unknown stop {target_id!r}")
        result = run_simulation(model, kind, target_id, baseline=self.baseline)
        target_name = (self._target_name(kind, target_id))
        impacts = [{
            "geoid": i.geoid, "name": _tract_label(model.tracts[i.geoid]),
            "score_before": i.score_before, "score_after": i.score_after,
            "score_drop": i.score_drop, "residents_affected": i.residents_affected,
            "zero_vehicle_pct": i.zero_vehicle_pct, "reason": i.reason,
        } for i in result["impacts"]]
        payload = {
            "id": None, "label": label, "kind": kind, "target_id": target_id,
            "target_name": target_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_residents_affected": result["total_residents_affected"],
            "avg_score_drop": result["avg_score_drop"],
            "best_fix": result["best_fix"],
            # API returns the top 25 tracts that actually lost access; the DB
            # persistence path stores every impacted tract (see DbSource).
            "impacts": [i for i in impacts if i["score_drop"] > 0][:25],
            "tract_scores": result["tract_scores"],
        }
        payload["id"] = self._persist_simulation(payload)
        return payload

    def _target_name(self, kind: str, target_id: str) -> str:
        if kind == "stop":
            stop = self.model.stops.get(target_id)
            return stop.name if stop else target_id
        meta = getattr(self, "_route_meta", {}).get(target_id, {})
        return f"Route {meta.get('short_name') or target_id}"

    def get_simulation(self, sim_id: str) -> dict | None:
        return self._load_simulation(sim_id)

    def compare(self, a_id: str, b_id: str) -> dict | None:
        a, b = self.get_simulation(a_id), self.get_simulation(b_id)
        if not a or not b:
            return None

        def summary(sim):
            worst = max(sim["impacts"], key=lambda i: i["score_drop"], default=None)
            return {"id": sim["id"], "label": sim["label"], "kind": sim["kind"],
                    "target_id": sim["target_id"], "target_name": sim.get("target_name"),
                    "total_residents_affected": sim["total_residents_affected"],
                    "avg_score_drop": sim["avg_score_drop"],
                    "worst_tract": ({"name": worst["name"], "score_drop": worst["score_drop"],
                                     "residents_affected": worst["residents_affected"]}
                                    if worst else None),
                    "best_fix": sim["best_fix"]}
        return {"a": summary(a), "b": summary(b)}


class SnapshotSource(BaseSource):
    demo_mode = True

    def __init__(self, payload: dict):
        super().__init__()
        self._payload = payload
        self._sims: dict[str, dict] = {}

    @classmethod
    def from_file(cls, path: Path = SNAPSHOT_PATH) -> "SnapshotSource":
        return cls(json.loads(Path(path).read_text()))

    def _load(self):
        p = self._payload
        self._datasets = (p.get("meta") or {}).get("datasets", [])
        stops = {s["stop_id"]: Stop(s["stop_id"], s["name"], s["lat"], s["lon"]) for s in p["stops"]}
        tracts, self._geometries, self._stored_baseline = [], {}, {}
        for t in p["tracts"]:
            tracts.append(Tract(t["geoid"], t["name"], t["lat"], t["lon"], t["population"],
                                t["median_income"], t["zero_vehicle_pct"]))
            if t.get("geometry"):
                self._geometries[t["geoid"]] = t["geometry"]
            if t.get("access"):
                self._stored_baseline[t["geoid"]] = t["access"]
        if len(self._stored_baseline) != len(tracts):
            self._stored_baseline = None
        self._route_meta = {r["route_id"]: r for r in p["routes"]}
        self._route_shapes = {r["route_id"]: r.get("shape") for r in p["routes"]}
        self._model = AccessModel(
            stops=stops,
            route_stops={k: set(v) for k, v in p["route_stops"].items()},
            pois=[Poi(x["poi_id"], x["name"], x["category"], x["lat"], x["lon"]) for x in p["pois"]],
            tracts=tracts)

    def _persist_simulation(self, payload: dict) -> str:
        sim_id = str(uuid.uuid4())
        self._sims[sim_id] = payload
        return sim_id

    def _load_simulation(self, sim_id: str) -> dict | None:
        return self._sims.get(sim_id)


class DbSource(BaseSource):
    demo_mode = False

    def __init__(self, database_url: str):
        super().__init__()
        self._url = database_url
        self._sims_cache: dict[str, dict] = {}

    def _conn(self):
        try:
            import psycopg
        except ImportError as exc:
            raise DataUnavailable("psycopg is not installed; run: pip install -r api/requirements.txt") from exc
        try:
            return psycopg.connect(self._url)
        except Exception as exc:  # noqa: BLE001
            raise DataUnavailable(f"cannot connect to Postgres via DATABASE_URL: {exc!r}") from exc

    def _load(self):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("select source, vintage, row_counts from datasets order by ingested_at")
                self._datasets = [{"source": r[0], "vintage": r[1], "row_counts": r[2]}
                                  for r in cur.fetchall()]
                cur.execute("select stop_id, name, ST_Y(geom::geometry), ST_X(geom::geometry) from stops")
                stops = {r[0]: Stop(r[0], r[1], r[2], r[3]) for r in cur.fetchall()}
                cur.execute("select route_id, short_name, long_name, color from routes")
                self._route_meta = {r[0]: {"route_id": r[0], "short_name": r[1],
                                           "long_name": r[2], "color": r[3]} for r in cur.fetchall()}
                cur.execute("select route_id, stop_id from route_stops")
                route_stops: dict[str, set[str]] = {}
                for rid, sid in cur.fetchall():
                    route_stops.setdefault(rid, set()).add(sid)
                cur.execute("select poi_id, name, category, ST_Y(geom::geometry), ST_X(geom::geometry) from pois")
                pois = [Poi(*r) for r in cur.fetchall()]
                cur.execute("""select geoid, name, ST_Y(centroid::geometry), ST_X(centroid::geometry),
                                      population, median_income, zero_vehicle_pct,
                                      ST_AsGeoJSON(geom::geometry) from tracts""")
                tracts, self._geometries = [], {}
                for r in cur.fetchall():
                    tracts.append(Tract(r[0], r[1], r[2], r[3], r[4], r[5],
                                        float(r[6]) if r[6] is not None else None))
                    if r[7]:
                        self._geometries[r[0]] = json.loads(r[7])
                cur.execute("select geoid, score_grocery, score_health, score_library, score_education, access_score from tract_access")
                stored = {r[0]: {"score_grocery": float(r[1]), "score_health": float(r[2]),
                                 "score_library": float(r[3]), "score_education": float(r[4]),
                                 "access_score": int(round(float(r[5])))} for r in cur.fetchall()}
                self._stored_baseline = stored if len(stored) == len(tracts) else None
        finally:
            conn.close()
        # NOTE: db/schema.sql (BRIEF §7) has no route-shapes table, so DB mode
        # returns routes without line geometry; snapshot mode includes shapes
        # parsed from GTFS shapes.txt. See NOTES.md.
        self._route_shapes = {}
        self._model = AccessModel(stops, route_stops, pois, tracts)

    def _persist_simulation(self, payload: dict) -> str:
        conn = self._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """insert into simulations(label, kind, target_id, total_residents_affected,
                                               avg_score_drop, best_fix)
                       values (%s,%s,%s,%s,%s,%s) returning id""",
                    (payload["label"], payload["kind"], payload["target_id"],
                     payload["total_residents_affected"], payload["avg_score_drop"],
                     json.dumps(payload["best_fix"]) if payload["best_fix"] else None))
                sim_id = str(cur.fetchone()[0])
                # persist ALL tract impacts (the API returns the top 25)
                model = self.model
                full = run_simulation(model, payload["kind"], payload["target_id"],
                                      baseline=self.baseline)
                cur.executemany(
                    """insert into simulation_impacts(simulation_id, geoid, score_before, score_after,
                                                      score_drop, residents_affected, reason)
                       values (%s,%s,%s,%s,%s,%s,%s)""",
                    [(sim_id, i.geoid, i.score_before, i.score_after, i.score_drop,
                      i.residents_affected, i.reason) for i in full["impacts"]])
        finally:
            conn.close()
        payload["id"] = sim_id
        self._sims_cache[sim_id] = payload
        return sim_id

    def _load_simulation(self, sim_id: str) -> dict | None:
        if sim_id in self._sims_cache:
            return self._sims_cache[sim_id]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""select label, kind, target_id, created_at, total_residents_affected,
                                      avg_score_drop, best_fix from simulations where id=%s""", (sim_id,))
                row = cur.fetchone()
                if not row:
                    return None
                cur.execute("""select geoid, score_before, score_after, score_drop,
                                      residents_affected, reason from simulation_impacts
                               where simulation_id=%s order by score_drop desc""", (sim_id,))
                impacts = []
                tract_scores = {}
                for r in cur.fetchall():
                    if int(r[3]) <= 0:
                        tract_scores[r[0]] = int(r[2])
                        continue
                    tract = self.model.tracts.get(r[0])
                    impacts.append({"geoid": r[0],
                                    "name": _tract_label(tract) if tract else f"Tract {r[0][-4:]}",
                                    "score_before": int(r[1]), "score_after": int(r[2]),
                                    "score_drop": int(r[3]), "residents_affected": int(r[4]),
                                    "zero_vehicle_pct": tract.zero_vehicle_pct if tract else None,
                                    "reason": r[5]})
                    tract_scores[r[0]] = int(r[2])
        finally:
            conn.close()
        payload = {"id": sim_id, "label": row[0], "kind": row[1], "target_id": row[2],
                   "target_name": self._target_name(row[1], row[2]),
                   "created_at": row[3].isoformat() if row[3] else None,
                   "total_residents_affected": row[4], "avg_score_drop": float(row[5]),
                   "best_fix": row[6], "impacts": impacts[:25], "tract_scores": tract_scores}
        self._sims_cache[sim_id] = payload
        return payload


def get_default_source() -> BaseSource:
    url = os.environ.get("DATABASE_URL")
    if url:
        return DbSource(url)
    if SNAPSHOT_PATH.exists():
        return SnapshotSource.from_file()
    raise DataUnavailable(
        "No data available: DATABASE_URL is not set and data/snapshot.json does not exist. "
        "Run the ingest scripts (see README) — the API never serves invented data.")
