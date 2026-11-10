"""Isthmus API — FastAPI app implementing BRIEF §9 exactly.

Run:  uvicorn api.main:app --reload --port 8000
Data: DATABASE_URL set -> Postgres/PostGIS (DbSource, simulations persisted).
      DATABASE_URL unset -> data/snapshot.json demo mode if it exists
      (produced by scripts/export_snapshot.py from real ingests), else every
      data endpoint answers 503 — never invented data.
"""
from __future__ import annotations

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .data import BaseSource, DataUnavailable, get_default_source
from .parsing import parse_scenario
from .scoring import CATEGORIES


class SimulateBody(BaseModel):
    kind: str
    target_id: str
    label: str | None = None


class ParseBody(BaseModel):
    text: str


def create_app(source: BaseSource | None = None) -> FastAPI:
    app = FastAPI(title="Isthmus API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])
    state: dict[str, BaseSource] = {}

    def src() -> BaseSource:
        if source is not None:
            return source
        if "source" not in state:
            state["source"] = get_default_source()
        return state["source"]

    @app.exception_handler(DataUnavailable)
    async def unavailable(_request: Request, exc: DataUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/meta")
    def meta():
        return src().meta()

    @app.get("/api/tracts")
    def tracts():
        return src().tracts_geojson()

    @app.get("/api/stops")
    def stops():
        return src().stops_geojson()

    @app.get("/api/routes")
    def routes():
        return src().routes_payload()

    @app.get("/api/pois")
    def pois(category: str | None = Query(default=None)):
        if category is not None and category not in CATEGORIES:
            return JSONResponse(status_code=400,
                                content={"detail": f"category must be one of {CATEGORIES}"})
        return src().pois_geojson(category)

    @app.post("/api/simulate")
    def simulate(body: SimulateBody):
        if body.kind not in ("stop", "route"):
            return JSONResponse(status_code=400,
                                content={"detail": "kind must be 'stop' or 'route'"})
        try:
            return src().simulate(body.kind, body.target_id, body.label)
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/api/simulations/{sim_id}")
    def get_simulation(sim_id: str):
        sim = src().get_simulation(sim_id)
        if sim is None:
            return JSONResponse(status_code=404, content={"detail": f"simulation {sim_id} not found"})
        return sim

    @app.get("/api/compare")
    def compare(a: str = Query(...), b: str = Query(...)):
        result = src().compare(a, b)
        if result is None:
            return JSONResponse(status_code=404,
                                content={"detail": "one or both simulations not found"})
        return result

    @app.post("/api/parse-scenario")
    def parse(body: ParseBody):
        s = src()
        match = parse_scenario(body.text, s.list_routes(), s.list_stops())
        if match is None:
            return {"matched": False,
                    "message": (f"Could not match '{body.text}' to a stop or route. "
                                "Try 'Close Route 80' or a stop name like 'Capitol'.")}
        return {"matched": True, **match}

    return app


app = create_app()
