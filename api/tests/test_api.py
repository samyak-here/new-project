"""Phase 5 — one API test with a tiny in-memory fixture (BRIEF §11).

The fixture is a hand-built SnapshotSource payload used ONLY to test the API
plumbing; it is never served as product data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from api.data import SnapshotSource  # noqa: E402
from api.main import create_app  # noqa: E402
from api.tests.test_scoring import LAT_M, make_model  # noqa: F401  (fixture geometry reuse)


def fixture_payload() -> dict:
    return {
        "meta": {"datasets": [{"source": "fixture", "vintage": "test", "row_counts": {}}]},
        "tracts": [{"geoid": "T1", "name": "Census Tract 1, Dane County, Wisconsin",
                    "population": 1000, "median_income": 50000, "zero_vehicle_pct": 12.5,
                    "lat": 43.0, "lon": -89.4, "geometry": None, "access": None}],
        "stops": [
            {"stop_id": "S1", "name": "Home stop", "lat": 43.0, "lon": -89.4},
            {"stop_id": "S2", "name": "Grocery stop", "lat": 43.0 + 2000 * LAT_M, "lon": -89.4},
            {"stop_id": "S3", "name": "Far stop", "lat": 43.0 + 9000 * LAT_M, "lon": -89.4},
        ],
        "routes": [
            {"route_id": "R1", "short_name": "80", "long_name": "Campus", "color": None,
             "stop_count": 2, "shape": None},
            {"route_id": "R2", "short_name": "84", "long_name": "Loop", "color": None,
             "stop_count": 2, "shape": None},
        ],
        "route_stops": {"R1": ["S1", "S2"], "R2": ["S1", "S3"]},
        "pois": [
            {"poi_id": "p-gro", "name": "Grocery", "category": "grocery",
             "lat": 43.0 + 2100 * LAT_M, "lon": -89.4},
            {"poi_id": "p-hea", "name": "Clinic", "category": "health",
             "lat": 43.0 + 100 * LAT_M, "lon": -89.4},
            {"poi_id": "p-lib", "name": "Library", "category": "library",
             "lat": 43.0 + 9200 * LAT_M, "lon": -89.4},
            {"poi_id": "p-edu", "name": "School", "category": "education",
             "lat": 43.0 - 300 * LAT_M, "lon": -89.4},
        ],
    }


def client() -> TestClient:
    return TestClient(create_app(SnapshotSource(fixture_payload())))


def test_meta_and_tracts():
    c = client()
    meta = c.get("/api/meta").json()
    assert meta["demo_mode"] is True
    assert "door-to-door" in meta["method"]["summary"]
    tracts = c.get("/api/tracts").json()
    assert tracts["type"] == "FeatureCollection"
    assert tracts["features"][0]["properties"]["access_score"] > 0


def test_simulate_route_closure_and_reload():
    c = client()
    resp = c.post("/api/simulate", json={"kind": "route", "target_id": "R1", "label": "Scenario A"})
    assert resp.status_code == 200
    sim = resp.json()
    assert sim["id"]
    assert sim["label"] == "Scenario A"
    top = sim["impacts"][0]
    assert top["score_after"] <= top["score_before"]
    assert top["score_drop"] > 0
    assert top["reason"]
    reloaded = c.get(f"/api/simulations/{sim['id']}")
    assert reloaded.status_code == 200
    assert reloaded.json()["total_residents_affected"] == sim["total_residents_affected"]


def test_simulate_unknown_target_404():
    c = client()
    assert c.post("/api/simulate", json={"kind": "route", "target_id": "ZZ"}).status_code == 404
    assert c.post("/api/simulate", json={"kind": "banana", "target_id": "R1"}).status_code == 400


def test_parse_scenario_and_compare():
    c = client()
    parsed = c.post("/api/parse-scenario", json={"text": "Close Route 80"}).json()
    assert parsed["matched"] is True and parsed["kind"] == "route" and parsed["target_id"] == "R1"
    miss = c.post("/api/parse-scenario", json={"text": "close the moon"}).json()
    assert miss["matched"] is False
    a = c.post("/api/simulate", json={"kind": "route", "target_id": "R1"}).json()
    b = c.post("/api/simulate", json={"kind": "stop", "target_id": "S1"}).json()
    cmp_ = c.get("/api/compare", params={"a": a["id"], "b": b["id"]}).json()
    assert cmp_["a"]["id"] == a["id"] and cmp_["b"]["id"] == b["id"]
    assert "worst_tract" in cmp_["a"]
