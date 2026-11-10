# Isthmus

**What breaks in Madison if this bus stop, route, or street closes?**

A map of Madison, WI where you close a Madison Metro bus stop or an entire route, the city re-colors by which neighborhoods just lost access to groceries, clinics, libraries, schools, and campus — and a ranked panel shows who is hit hardest, why, and where adding one temporary stop would restore the most access.

Madison sits on an isthmus between Lake Mendota and Lake Monona, so a few routes carry almost everything across the city. Close one, and the damage is visible instantly.

## Why this exists

The pattern is copied from real 2026 college hackathon winners on Devpost:

- **Ripple** (HackGT 13) — GTFS + Census + OpenStreetMap in Postgres, simulate a transit closure on a heatmap, find the best new spot: https://devpost.com/software/ripple-vepi8b
- **Vigil** (Cal Hacks 13.0, Winner) — a ranked queue that says who to check next and why, instead of raw alarms: https://devpost.com/software/vigil-aewt3u
- **Tribune** (TreeHacks 2026, Winner) — real public records in a real database, searched in natural language, with evidence: https://devpost.com/software/tribune
- **EcoCity** (HackHarvard 2026) — explore, run an intervention, compare outcomes with an auditable method trail: https://devpost.com/software/ecocity-b6rv37
- **Orbit Health** (Cal Hacks 13.0, Winner) — the clickable map is the product: https://devpost.com/software/orbit-health

Isthmus is that formula, built for Madison with Madison's own open data.

## How it works

- **Database:** Postgres + PostGIS holds Madison Metro GTFS stops/routes, Census ACS tracts (population, income, zero-vehicle households), and OpenStreetMap places (groceries, health, libraries, education).
- **Access Score (0–100):** for each census tract, how fast it can reach the nearest place in each of the four categories by walk + bus, using a transparent proxy model — the full formula and its limits are documented in `BRIEF.md` §6 and shown in the app's Method panel.
- **Simulate:** close a stop or a route and every score is recomputed from the database. The **Impact Queue** ranks neighborhoods by access lost and estimated residents affected, each with a one-sentence reason. **Best Fix** searches for the one added stop that restores the most access.
- **Compare:** save two scenarios and compare their total impact side by side.

## For builders

**Start with [`BRIEF.md`](BRIEF.md)** — it is the full, Claude-Code-ready project brief: data sources, exact scoring definition, database schema, API surface, UI/design system, build phases with acceptance criteria, and what is explicitly out of scope. [`CLAUDE.md`](CLAUDE.md) has the short working rules. [`NOTES.md`](NOTES.md) records the engineering decisions and deviations made while building; [`RESULTS.md`](RESULTS.md) records what was verified and how.

## Status

Built — Phases 0–5 implemented (scaffold, ingest, scoring, API, web app, tests). See `RESULTS.md` for verification details.

## Running it

### Option A — full stack with Postgres (recommended)

```bash
cp .env.example .env            # set POSTGRES_PASSWORD
docker compose up -d db         # Postgres 16 + PostGIS, schema auto-created from db/schema.sql

python3 -m venv .venv && .venv/bin/pip install -r api/requirements.txt
export DATABASE_URL=postgresql://isthmus:YOUR_PASSWORD@localhost:5432/isthmus

.venv/bin/python scripts/ingest_gtfs.py      # Madison Metro GTFS
.venv/bin/python scripts/ingest_census.py    # ACS tracts (see note below)
.venv/bin/python scripts/ingest_pois.py      # OpenStreetMap POIs via Overpass
.venv/bin/python scripts/compute_baseline.py # baseline Access Scores -> tract_access

.venv/bin/uvicorn api.main:app --port 8000   # API
npm install && npm run dev                   # web app on http://localhost:3000
```

Census note: `api.census.gov` now requires a free API key. With
`CENSUS_API_KEY` set the script uses it directly; without one it falls back
to Census Reporter, which republishes the same ACS 5-year tables (see
`NOTES.md`). Overpass can be slow; the POI script retries and falls back to a
mirror automatically, and logs the exact error if both fail.

### Option B — demo mode without a database

```bash
.venv/bin/python scripts/ingest_gtfs.py   --dry-run --out data/gtfs.json
.venv/bin/python scripts/ingest_census.py --dry-run --out data/census.json
.venv/bin/python scripts/ingest_pois.py   --dry-run --out data/pois.json
.venv/bin/python scripts/export_snapshot.py   # writes data/snapshot.json from the real dry-runs

.venv/bin/uvicorn api.main:app --port 8000    # no DATABASE_URL -> serves the snapshot
npm install && npm run dev
```

Demo mode serves only data that came from real ingests. If neither
`DATABASE_URL` nor `data/snapshot.json` exists, the API answers 503 with
setup instructions — it never invents data. Simulations in demo mode are
computed live and held in memory; in DB mode they persist.

### Tests

```bash
.venv/bin/python -m pytest api/tests -q   # scoring unit tests + API fixture test
npm run build                             # production build must pass
```

## Layout

```
db/schema.sql          Postgres + PostGIS schema (BRIEF §7, verbatim)
docker-compose.yml     db service (postgis/postgis:16-3.4)
scripts/               ingest_gtfs / ingest_census / ingest_pois / compute_baseline / export_snapshot
api/scoring.py         the one implementation of the Access Score (BRIEF §6)
api/data.py            data sources: Postgres | JSON snapshot | honest 503
api/main.py            FastAPI app (BRIEF §9 endpoints)
api/parsing.py         rule-based scenario parser (no LLM)
app/, components/      Next.js app: map, Impact Queue, Best Fix, Compare, Method
design/altius/         Altius design tokens the UI is built from
```
