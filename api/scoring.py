"""Isthmus Access Score — the ONE implementation of BRIEF.md §6.

Pure Python over lat/lon rows (haversine), so it is unit-testable without a
database. Postgres/PostGIS remains the store; this module is used identically
by scripts/compute_baseline.py, POST /api/simulate, and the Best Fix search.
No copy-pasted variants anywhere.

Model (BRIEF §6, a transparent proxy — not door-to-door directions):
  * A tract is represented by its census tract centroid.
  * Walking radius W = 800 m.
  * A POI is reachable from a tract if some route R serves both a stop S1
    within W of the tract centroid and a stop S2 within W of the POI,
    or the POI itself is within W of the centroid (walk the whole way).
  * Time proxy = walk(tract->S1)/80 m/min + great-circle(S1->S2)/400 m/min
    + walk(S2->POI)/80 m/min. Walk-only: distance/80.
  * Category score = score of the fastest reachable POI in the category:
    100 at <=15 min, linear to 0 at 45 min, unreachable = 0.
  * Access Score = mean of the 4 category scores, rounded to an integer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

WALK_RADIUS_M = 800.0
WALK_SPEED_M_PER_MIN = 80.0
VEHICLE_SPEED_M_PER_MIN = 400.0
CATEGORIES = ("grocery", "health", "library", "education")
CATEGORY_LABELS = {
    "grocery": "Grocery",
    "health": "Health",
    "library": "Library",
    "education": "Education / Campus",
}
EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def time_to_score(minutes: float | None) -> float:
    """BRIEF §6 score curve: 100 at <=15 min, linear to 0 at 45 min."""
    if minutes is None:
        return 0.0
    if minutes <= 15.0:
        return 100.0
    if minutes >= 45.0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (45.0 - minutes) / 30.0))


@dataclass(frozen=True)
class Stop:
    stop_id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Poi:
    poi_id: str
    name: str | None
    category: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Tract:
    geoid: str
    name: str | None
    lat: float  # centroid
    lon: float  # centroid
    population: int = 0
    median_income: int | None = None
    zero_vehicle_pct: float | None = None


@dataclass(frozen=True)
class ExtraStop:
    """A hypothetical added stop (Best Fix candidate), attached to one route."""
    lat: float
    lon: float
    route_id: str
    label: str = "best-fix"


class AccessModel:
    """Precomputed proximity indexes over stops/POIs; scores tracts under closures."""

    def __init__(self, stops: dict[str, Stop], route_stops: dict[str, set[str]],
                 pois: list[Poi], tracts: list[Tract]):
        self.stops = stops
        self.route_stops = {r: set(s) for r, s in route_stops.items()}
        self.pois = pois
        self.tracts = {t.geoid: t for t in tracts}
        # stop -> routes serving it
        self.stop_routes: dict[str, set[str]] = {}
        for route_id, sids in self.route_stops.items():
            for sid in sids:
                self.stop_routes.setdefault(sid, set()).add(route_id)
        # stops within W of each tract centroid / each POI (exact, brute force)
        self._tract_stops: dict[str, list[tuple[str, float]]] = {
            t.geoid: self._within(t.lat, t.lon, stops.values(), lambda s: s.stop_id)
            for t in tracts
        }
        self._poi_stops: dict[str, list[tuple[str, float]]] = {
            p.poi_id: self._within(p.lat, p.lon, stops.values(), lambda s: s.stop_id)
            for p in pois
        }
        self._pois_by_category: dict[str, list[Poi]] = {c: [] for c in CATEGORIES}
        for p in pois:
            if p.category in self._pois_by_category:
                self._pois_by_category[p.category].append(p)

    @staticmethod
    def _within(lat: float, lon: float, points, id_of) -> list[tuple[str, float]]:
        out = []
        for pt in points:
            d = haversine_m(lat, lon, pt.lat, pt.lon)
            if d <= WALK_RADIUS_M:
                out.append((id_of(pt), d))
        return out

    # -- core ---------------------------------------------------------------
    def _time_to_stops(self, tract: Tract, removed_routes: set[str],
                       removed_stops: set[str], extra: ExtraStop | None) -> dict[str, float]:
        """Fastest proxy time from this tract to every stop reachable by bus."""
        boardings: list[tuple[str, float, set[str]]] = []  # (stop_id, walk_m, routes)
        for sid, dist in self._tract_stops[tract.geoid]:
            if sid in removed_stops:
                continue
            routes = self.stop_routes.get(sid, set()) - removed_routes
            if routes:
                boardings.append((sid, dist, routes))
        if extra is not None and extra.route_id not in removed_routes:
            d = haversine_m(tract.lat, tract.lon, extra.lat, extra.lon)
            if d <= WALK_RADIUS_M:
                boardings.append(("__extra__", d, {extra.route_id}))
        best: dict[str, float] = {}
        # board at S1, ride route R to every stop S2 on R
        stops_by_route: dict[str, list[str]] = {}
        for route_id, sids in self.route_stops.items():
            if route_id in removed_routes:
                continue
            stops_by_route[route_id] = [s for s in sids if s not in removed_stops]
        for s1_id, walk_m, routes in boardings:
            s1 = self.stops.get(s1_id)
            s1_lat, s1_lon = (extra.lat, extra.lon) if s1_id == "__extra__" and extra else (s1.lat, s1.lon)
            walk_min = walk_m / WALK_SPEED_M_PER_MIN
            for route_id in routes:
                targets = list(stops_by_route.get(route_id, []))
                if extra is not None and extra.route_id == route_id:
                    targets = targets + ["__extra__"]
                for s2_id in targets:
                    if s2_id == "__extra__" and extra:
                        s2_lat, s2_lon = extra.lat, extra.lon
                    else:
                        s2 = self.stops[s2_id]
                        s2_lat, s2_lon = s2.lat, s2.lon
                    t = walk_min + haversine_m(s1_lat, s1_lon, s2_lat, s2_lon) / VEHICLE_SPEED_M_PER_MIN
                    if s2_id not in best or t < best[s2_id]:
                        best[s2_id] = t
        return best

    def category_times(self, tract: Tract, removed_routes=frozenset(),
                       removed_stops=frozenset(), extra: ExtraStop | None = None) -> dict[str, float | None]:
        """Fastest reachable-POI time per category for one tract."""
        time_to_stop = self._time_to_stops(tract, set(removed_routes), set(removed_stops), extra)
        out: dict[str, float | None] = {}
        for cat in CATEGORIES:
            best: float | None = None
            for poi in self._pois_by_category[cat]:
                # walk the whole way
                d = haversine_m(tract.lat, tract.lon, poi.lat, poi.lon)
                if d <= WALK_RADIUS_M:
                    t = d / WALK_SPEED_M_PER_MIN
                    if best is None or t < best:
                        best = t
                # bus: ride to a stop near the POI, then walk
                poi_stops = list(self._poi_stops[poi.poi_id])
                if extra is not None:
                    de = haversine_m(extra.lat, extra.lon, poi.lat, poi.lon)
                    if de <= WALK_RADIUS_M:
                        poi_stops = poi_stops + [("__extra__", de)]
                for s2_id, walk2_m in poi_stops:
                    if s2_id in removed_stops:
                        continue
                    ride = time_to_stop.get(s2_id)
                    if ride is None:
                        continue
                    t = ride + walk2_m / WALK_SPEED_M_PER_MIN
                    if best is None or t < best:
                        best = t
            out[cat] = best
        return out

    def score_tract(self, tract: Tract, removed_routes=frozenset(),
                    removed_stops=frozenset(), extra: ExtraStop | None = None) -> dict:
        times = self.category_times(tract, removed_routes, removed_stops, extra)
        cats = {c: round(time_to_score(times[c]), 2) for c in CATEGORIES}
        access = round(sum(cats.values()) / len(CATEGORIES))
        return {**{f"score_{c}": cats[c] for c in CATEGORIES}, "access_score": access,
                "times": {c: (round(times[c], 2) if times[c] is not None else None) for c in CATEGORIES}}

    def compute_all(self, removed_routes=frozenset(), removed_stops=frozenset(),
                    extra: ExtraStop | None = None) -> dict[str, dict]:
        return {geoid: self.score_tract(t, removed_routes, removed_stops, extra)
                for geoid, t in self.tracts.items()}


@dataclass
class Impact:
    geoid: str
    name: str | None
    score_before: int
    score_after: int
    score_drop: int
    residents_affected: int
    zero_vehicle_pct: float | None
    reason: str


def _reason(tract: Tract, before: dict, after: dict, kind: str) -> str:
    drops = {c: before[f"score_{c}"] - after[f"score_{c}"] for c in CATEGORIES}
    worst = max(drops, key=lambda c: drops[c])
    label = CATEGORY_LABELS[worst].lower()
    if drops[worst] <= 0:
        return "Access dipped slightly across several categories for this tract."
    return (f"{label.capitalize()} access fell the most here "
            f"({before[f'score_{worst}']:.0f} to {after[f'score_{worst}']:.0f}) "
            f"after the {kind} closure.")


def run_simulation(model: AccessModel, kind: str, target_id: str,
                   baseline: dict[str, dict] | None = None) -> dict:
    """Run a closure and return impacts + best fix. The single simulation path.

    Returns {impacts: [Impact...] sorted by drop desc, tract_scores: {geoid: after},
             total_residents_affected, avg_score_drop, best_fix | None}
    """
    if baseline is None:
        baseline = model.compute_all()
    if kind == "route":
        removed_routes, removed_stops = {target_id}, set()
    elif kind == "stop":
        removed_routes, removed_stops = set(), {target_id}
    else:
        raise ValueError(f"kind must be 'stop' or 'route', got {kind!r}")
    after_all = model.compute_all(removed_routes, removed_stops)
    impacts: list[Impact] = []
    total_residents = 0
    total_drop = 0.0
    for geoid, tract in model.tracts.items():
        b, a = baseline[geoid], after_all[geoid]
        drop = int(b["access_score"]) - int(a["access_score"])
        residents = round(tract.population * max(drop, 0) / 100)
        total_residents += residents
        total_drop += max(drop, 0)
        impacts.append(Impact(
            geoid=geoid, name=tract.name, score_before=int(b["access_score"]),
            score_after=int(a["access_score"]), score_drop=int(drop),
            residents_affected=residents, zero_vehicle_pct=tract.zero_vehicle_pct,
            reason=_reason(tract, b, a, kind) if drop > 0 else "No change in Access Score for this tract.",
        ))
    impacts.sort(key=lambda i: (-i.score_drop, -i.residents_affected))
    avg_drop = round(total_drop / len(impacts), 2) if impacts else 0.0
    best_fix = find_best_fix(model, kind, target_id, baseline, after_all, impacts,
                             removed_routes, removed_stops)
    return {
        "impacts": impacts,
        "tract_scores": {g: int(s["access_score"]) for g, s in after_all.items()},
        "total_residents_affected": total_residents,
        "avg_score_drop": avg_drop,
        "best_fix": best_fix,
    }


def find_best_fix(model: AccessModel, kind: str, target_id: str,
                  baseline: dict[str, dict], after_all: dict[str, dict],
                  impacts: list[Impact], removed_routes: set[str],
                  removed_stops: set[str]) -> dict | None:
    """BRIEF §6 Best Fix heuristic. Recovery is summed over affected tracts only
    (tracts whose score dropped) — documented in NOTES.md."""
    affected = [i for i in impacts if i.score_drop > 0]
    if not affected:
        return None
    affected_geoids = [i.geoid for i in affected]
    surviving_routes = set(model.route_stops) - removed_routes
    if not surviving_routes:
        return None

    def nearest_surviving_route(lat: float, lon: float) -> str | None:
        best_r, best_d = None, float("inf")
        for sid, stop in model.stops.items():
            if sid in removed_stops:
                continue
            routes = model.stop_routes.get(sid, set()) & surviving_routes
            if not routes:
                continue
            d = haversine_m(lat, lon, stop.lat, stop.lon)
            if d < best_d:
                best_d, best_r = d, sorted(routes)[0]
        return best_r

    candidates: list[ExtraStop] = []
    seen: set[tuple[float, float, str]] = set()

    def add_candidate(lat: float, lon: float, note_route: str | None):
        if note_route is None:
            return
        key = (round(lat, 5), round(lon, 5), note_route)
        if key in seen:
            return
        seen.add(key)
        candidates.append(ExtraStop(lat=lat, lon=lon, route_id=note_route))

    # (b) centroid of each of the 5 worst-hit tracts, on the nearest surviving route
    for imp in affected[:5]:
        t = model.tracts[imp.geoid]
        add_candidate(t.lat, t.lon, nearest_surviving_route(t.lat, t.lon))
    # (a) stops that lost all service from this closure, re-served by the
    #     nearest surviving route (capped at the 20 closest to the worst tract)
    if kind == "route":
        lost_stop_ids = [sid for sid, rs in model.stop_routes.items() if rs and rs <= removed_routes]
    else:
        lost_stop_ids = [target_id]
    worst = model.tracts[affected[0].geoid]
    lost_stop_ids.sort(key=lambda sid: haversine_m(worst.lat, worst.lon,
                                                   model.stops[sid].lat, model.stops[sid].lon)
                       if sid in model.stops else float("inf"))
    for sid in lost_stop_ids[:20]:
        if sid not in model.stops:
            continue
        s = model.stops[sid]
        add_candidate(s.lat, s.lon, nearest_surviving_route(s.lat, s.lon))

    best: dict | None = None
    for cand in candidates:
        recovery = 0.0
        for geoid in affected_geoids:
            t = model.tracts[geoid]
            s = model.score_tract(t, removed_routes, removed_stops, extra=cand)
            recovery += max(0, s["access_score"] - after_all[geoid]["access_score"])
        if recovery > 0 and (best is None or recovery > best["recovered_score"]):
            route_name = cand.route_id
            best = {"lat": cand.lat, "lon": cand.lon, "route_id": route_name,
                    "recovered_score": round(recovery, 1),
                    "note": (f"Best fix found: a temporary stop here, served by route "
                             f"{route_name}, restores about {recovery:.0f} Access Score "
                             f"points summed across the affected tracts.")}
    return best
