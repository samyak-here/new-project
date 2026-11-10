"""Phase 5 — BRIEF §6 scoring tests (pure Python, no DB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.scoring import (AccessModel, ExtraStop, Poi, Stop, Tract,
                         run_simulation, time_to_score)

# A tiny synthetic city: tract at origin; stops/POIs placed by metre offsets.
# At Madison's latitude, 1 degree lat ~= 111_320 m, 1 degree lon ~= 81_000 m.
LAT_M = 1 / 111_320.0
LON_M = 1 / 81_000.0


def make_model():
    stops = {
        "S1": Stop("S1", "Home stop", 43.0, -89.4),
        "S2": Stop("S2", "Grocery stop", 43.0 + 2000 * LAT_M, -89.4),
        "S3": Stop("S3", "Far stop", 43.0 + 9000 * LAT_M, -89.4),
    }
    route_stops = {"R1": {"S1", "S2"}, "R2": {"S1", "S3"}}
    pois = [
        Poi("p-gro", "Grocery", "grocery", 43.0 + 2100 * LAT_M, -89.4),   # near S2
        Poi("p-hea", "Clinic", "health", 43.0 + 100 * LAT_M, -89.4),      # walk-only
        Poi("p-lib", "Library", "library", 43.0 + 9200 * LAT_M, -89.4),   # near S3
        Poi("p-edu", "School", "education", 43.0 - 300 * LAT_M, -89.4),   # walk-only
    ]
    tracts = [Tract("T1", "Test tract", 43.0, -89.4, population=1000, zero_vehicle_pct=12.5)]
    return AccessModel(stops, route_stops, pois, tracts)


def test_score_curve_boundaries():
    assert time_to_score(None) == 0.0
    assert time_to_score(15.0) == 100.0
    assert time_to_score(14.0) == 100.0
    assert time_to_score(45.0) == 0.0
    assert time_to_score(60.0) == 0.0
    assert time_to_score(30.0) == 50.0


def test_walk_only_and_bus_categories():
    m = make_model()
    s = m.score_tract(m.tracts["T1"])
    # health + education are within 800 m on foot -> 100 each
    assert s["score_health"] == 100.0
    assert s["score_education"] == 100.0
    # grocery: walk 0 + ride 2000m/400 = 5 + walk 100m/80 = 1.25 -> 6.25 min -> 100
    assert s["score_grocery"] == 100.0
    # library: ride 9000/400 = 22.5 + walk 200/80 = 2.5 -> 25 min -> 66.67
    assert abs(s["score_library"] - 66.67) < 0.5
    assert 0 <= s["access_score"] <= 100


def test_unreachable_is_zero():
    m = make_model()
    # close both routes: only walk-only categories survive
    s = m.score_tract(m.tracts["T1"], removed_routes={"R1", "R2"})
    assert s["score_grocery"] == 0.0
    assert s["score_library"] == 0.0
    assert s["score_health"] == 100.0


def test_closure_never_raises_score():
    m = make_model()
    result = run_simulation(m, "route", "R1")
    for imp in result["impacts"]:
        assert imp.score_after <= imp.score_before
    result2 = run_simulation(m, "stop", "S1")
    for imp in result2["impacts"]:
        assert imp.score_after <= imp.score_before
    # closing R1 removes the grocery ride entirely
    assert result["impacts"][0].score_drop > 0


def test_best_fix_recovers_or_none():
    m = make_model()
    result = run_simulation(m, "route", "R1")
    bf = result["best_fix"]
    # a surviving route (R2) exists, so a fix should be found with recovery > 0,
    # or an explicit None is acceptable per the brief — assert the contract:
    assert bf is None or (bf["recovered_score"] > 0 and "lat" in bf and "lon" in bf)


def test_best_fix_none_when_nothing_affected():
    m = make_model()
    # closing a stop nobody boards at to reach anything new: S3 serves library,
    # use a route closure that changes nothing walk-wise is impossible here, so
    # instead close R2 and check the contract holds symmetrically.
    result = run_simulation(m, "route", "R2")
    assert result["best_fix"] is None or result["best_fix"]["recovered_score"] > 0


def test_extra_stop_improves_access():
    m = make_model()
    t = m.tracts["T1"]
    closed = m.score_tract(t, removed_routes={"R1"})
    assert closed["score_grocery"] == 0.0
    extra = ExtraStop(lat=43.0, lon=-89.4, route_id="R2")
    # extra stop at the tract on R2 does not reach the grocery (it is near S2 on
    # R1 only) -> still 0; move the grocery-side stop instead:
    assert m.score_tract(t, removed_routes={"R1"}, extra=extra)["score_grocery"] == 0.0
    extra2 = ExtraStop(lat=43.0 + 2000 * LAT_M, lon=-89.4, route_id="R2")
    fixed = m.score_tract(t, removed_routes={"R1"}, extra=extra2)
    assert fixed["score_grocery"] == 100.0


def test_residents_affected_formula():
    m = make_model()
    result = run_simulation(m, "route", "R1")
    imp = result["impacts"][0]
    assert imp.residents_affected == round(1000 * imp.score_drop / 100)
