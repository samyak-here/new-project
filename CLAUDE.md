# CLAUDE.md — Isthmus

Read `BRIEF.md` first. It is the single source of truth for this project: idea, data sources, Access Score formula (§6), database schema (§7), API (§9), UI rules (§10), and build phases (§11).

## Project in one line

Isthmus: a Madison, WI transit what-if simulator. Close a bus stop or route on a map, see which neighborhoods lose access to groceries / health / libraries / education, ranked, with a best-fix suggestion.

## Stack (fixed, see BRIEF §8)

- Next.js (App Router) + TypeScript + Tailwind + shadcn/ui — web app at repo root
- MapLibre GL + Deck.gl for the map (no Mapbox token, no paid tiles)
- FastAPI (Python 3.12) in `api/` — all scoring lives here, once, in `api/scoring.py`
- Postgres 16 + PostGIS via `docker-compose.yml` — schema in `db/schema.sql` (BRIEF §7)

## Commands

```bash
docker compose up -d          # PostGIS
python scripts/ingest_gtfs.py && python scripts/ingest_census.py && python scripts/ingest_pois.py
python scripts/compute_baseline.py
uvicorn api.main:app --reload # API
npm run dev                   # web
```

## Working rules

- Build phase by phase (BRIEF §11, Phases 0–5 in order). Verify a phase's acceptance criteria before starting the next. Commit after each phase, message naming the phase.
- Never fabricate data. If GTFS / Census / Overpass fails, retry once, then stop and report the exact error and URL. No fake stops, tracts, POIs, or scores, ever.
- All Access Scores come from the single scoring function (BRIEF §6) reading the database. Never hardcode a score or result in frontend code.
- Out of scope (BRIEF §12): auth, payments, GTFS-RT, door-to-door routing, LLM parsing, other cities. Do not build them.
- Ambiguous + reversible → pick the simpler option, note it in `NOTES.md`. Changes the data model, the scoring formula, or the stack → stop and ask.
- Before saying "done": Phase 5 tests green (scoring unit tests incl. "a closure never raises a score", one `/api/simulate` API test), `npm run build` clean, and the 60-second demo in BRIEF §4 works end to end.
