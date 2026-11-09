# Isthmus — Full Project Brief

> Give this file to Claude Code as the single source of truth. Build in the phase order below. Do not invent data, scores, or features that are not in this brief. If a data source below fails, stop and report exactly what failed instead of substituting fake data.

---

## 1. The idea in one line

**Isthmus — what breaks in Madison if this bus stop, route, or street closes?**

A web app with a real database, a map of Madison, WI, and a what-if simulator: a user closes a Madison Metro bus stop or an entire route, the map re-colors by which neighborhoods just lost access to groceries, clinics, libraries, schools, and campus, and a ranked panel shows which neighborhoods are hit hardest — and where adding one temporary stop would restore the most access.

Madison sits on an isthmus between Lake Mendota and Lake Monona, so a handful of routes carry almost everything across the city. That geography is what makes closures dramatic and the demo instantly readable.

## 2. Why this project (the pattern it is copying)

This brief is distilled from real winners/notable projects at big 2026 college hackathons on Devpost. Steal these proven moves, do not reinvent them:

| Pattern to steal | Source project | What to copy exactly |
|---|---|---|
| Real public records in a real database + natural-language search over it, with evidence | **Tribune** — TreeHacks 2026 (Stanford), Winner — https://devpost.com/software/tribune | A real corpus (here: GTFS + Census + OSM) in Postgres, queried — never hardcoded results |
| What-if closure simulation on GTFS + Census + OpenStreetMap in Postgres, heatmap, optimal new-spot finder, equity insight | **Ripple** — HackGT 13 — https://devpost.com/software/ripple-vepi8b | The whole core loop of Isthmus: simulate a closure → map impact → find the best fix |
| Ranked queue instead of raw data: "check this next, and here is why" | **Vigil** — Cal Hacks 13.0, Winner — https://devpost.com/software/vigil-aewt3u | The right-hand Impact Queue: ranked neighborhoods, each with a plain-English reason |
| Explore → run an intervention → compare outcomes side by side, with an auditable evidence/method trail | **EcoCity** — HackHarvard 2026 — https://devpost.com/software/ecocity-b6rv37 | Save Scenario A and B, compare them, and always show the methodology + data sources in the UI |
| The clickable map IS the product | **Orbit Health** — Cal Hacks 13.0, Winner — https://devpost.com/software/orbit-health | Full-screen map first. Charts support the map, they do not replace it |

Non-negotiable lesson from all five: **winners ship real data in a real database, a visualization you can touch, and an insight the user did not have to compute themselves.** No mock data, no hardcoded charts, no generic admin dashboard.

## 3. Who it is for

- Primary demo user: a fellow UW–Madison student, a Madison resident, or a hiring manager opening the link cold. They must "get it" in 10 seconds with no explanation.
- Secondary: city/transit-curious people who want to argue about a route change with evidence instead of vibes.

## 4. The 60-second demo (this exact flow must work)

1. App opens to a full-screen dark map of Madison between the lakes. Census tracts are colored by **Access Score** (0–100, defined in §6). Stops are dots, routes are lines.
2. User searches "Capitol" or clicks a stop on the UW campus, or picks **Route 80** or **BRT Route A** from the route list, and clicks **Simulate closure**.
   - Also support typing a scenario into one text box, rule-based parsing in the MVP (see §9): e.g. `Close Route 80` or `Close stop 1234`.
3. The map re-renders: tracts that lost access shift toward red, tracts unaffected stay calm.
4. The right panel — the **Impact Queue** — ranks the hit neighborhoods: tract name/area label, Access Score before → after, drop size, estimated residents affected, % zero-vehicle households, and one plain-English reason ("Nearest grocery was only reachable via Route A from this tract").
5. A **Best Fix** card appears: "Add a temporary stop here restores the most access" — one map pin, with the estimated score recovery if that stop existed on a still-running route.
6. User saves this as **Scenario A**, resets, closes a different route as **Scenario B**, and opens **Compare**: two small maps + a table of total residents affected, worst tract, and average Access Score drop, A vs B.
7. Everywhere the numbers appear, a **Method** link opens a panel stating the data sources, the vintage of each dataset, and the Access Score formula from §6. Auditable, like EcoCity.

## 5. Data sources (all public, all verified to exist — use only these)

1. **Madison Metro GTFS (static)** — stops (with lat/lon), routes, trips, stop_times, shapes.
   - Developer info: https://www.cityofmadison.com/metro/business/information-for-developers
   - Feed file linked from that page (known location: `http://transitdata.cityofmadison.com/GTFS/mmt_gtfs.zip` — if this 404s, fetch the current link from the developer page, do not guess another URL).
   - Sanity scale from a recent feed snapshot: ~29 routes, ~1,681 stops. Feeds change; ingest must assert `stops > 1000` and `routes > 20`, and log the actual counts — never assert the exact numbers above.
2. **US Census ACS 5-year (tract level, Dane County, WI — state FIPS 55, county 025)** — via the Census API (no key needed for low volume): total population, median household income, zero-vehicle households / total households. Use the most recent ACS 5-year release the API returns and record the year in the `datasets` table (§7).
3. **OpenStreetMap POIs** — via Overpass API for the Madison bounding box, exactly these categories:
   - grocery: `shop=supermarket`, `shop=convenience` (label the category "Grocery")
   - clinic/hospital: `amenity=clinic`, `amenity=hospital`, `amenity=pharmacy` (label "Health")
   - library: `amenity=library` (label "Library")
   - school: `amenity=school`, `amenity=university`, `amenity=college` (label "Education / Campus")
   - Keep the OSM element id and name on every POI row. Unnamed POIs are kept but display as their category name.
4. **Basemap** — MapLibre GL with a free dark basemap style (e.g. CARTO basemaps). **No Mapbox token, no paid tiles.** If a style URL fails, fall back to OSM raster tiles.

Do NOT scrape Zillow, Google Maps, or any site that forbids it. Do NOT use any dataset not listed here in the MVP.

## 6. The Access Score — exact definition (implement this, document it in the UI)

This is a transparent proxy model, not a routing engine. Say so in the Method panel, worded as: "Access Score is a simplified transit-access proxy, not door-to-door directions."

Definitions:

- A tract is represented by its census tract centroid.
- Walking radius `W = 800 m`. A stop is *walkable* from a tract if it is within `W` of the centroid (PostGIS `ST_DWithin` on geography).
- A POI is *reachable* from a tract for a category if: there exists a route `R` and two stops `S1, S2` both served by `R`, where `S1` is walkable from the tract centroid and `S2` is within `W` of the POI, **or** the POI itself is within `W` of the tract centroid (walking the whole way).
- `transit_time_proxy_minutes` for a reachable POI = walk time tract→S1 (distance / 80 m/min) + in-vehicle proxy (great-circle S1→S2 distance / 400 m/min, roughly city bus average with stops) + walk time S2→POI. For walk-only reachability it is just walk time.
- Category score for a tract = score of its *fastest* reachable POI in that category:
  - `100` if time ≤ 15 min, then linear down to `0` at 45 min: `score = clamp(100 * (45 - t) / 30, 0, 100)`. Unreachable = `0`.
- **Access Score (a tract) = mean of its four category scores** (Grocery, Health, Library, Education/Campus), rounded to an integer.
- A simulation removes a set of stops (one stop, or every stop_times row of one route — closing a route removes that route from reachability, stops shared with other routes stay for those routes). All scores are recomputed with the exact same function. **Closing something must never raise any tract's score — add a test for this.**
- Residents affected for a tract in a simulation = tract population × (baseline_score − scenario_score) / 100, rounded. Label it "estimated residents affected" everywhere.
- Best Fix: candidate points are (a) each closed stop, evaluated as restored on any one still-running route that also serves stops near the tracts that lost the most, and (b) the centroid of each of the 5 worst-hit tracts, snapped to the nearest existing stop location on a still-running route. Evaluate each candidate by re-running the score function with it added; pick the one with the largest total Access Score recovery across all tracts. Show only the best one in the MVP. This is a heuristic search — label it "best fix found" not "optimal".

Keep the scoring in ONE shared function/module used by baseline computation, simulations, and Best Fix. No copy-pasted variants.

## 7. Database — Postgres + PostGIS (this is the centerpiece, do it properly)

Run locally via `docker-compose.yml` (Postgres 16 + PostGIS). All coordinates stored as `geography(Point, 4326)` (or geometry + GIST indexes — pick geography and be consistent).

```sql
create extension if not exists postgis;

create table datasets (
  id serial primary key,
  source text not null,            -- 'madison_gtfs' | 'acs' | 'osm'
  vintage text,                    -- e.g. GTFS feed date / ACS year / OSM extract date
  ingested_at timestamptz not null default now(),
  row_counts jsonb not null        -- actual counts logged at ingest, e.g. {"stops": 1681}
);

create table routes (
  route_id text primary key,       -- GTFS route_id
  short_name text, long_name text,
  color text
);

create table stops (
  stop_id text primary key,        -- GTFS stop_id
  name text not null,
  geom geography(Point,4326) not null
);

create table route_stops (         -- from trips + stop_times, deduplicated
  route_id text not null references routes(route_id),
  stop_id  text not null references stops(stop_id),
  primary key (route_id, stop_id)
);

create table tracts (
  geoid text primary key,          -- census tract GEOID
  name text,                       -- tract label for display
  population int not null default 0,
  median_income int,
  zero_vehicle_pct numeric,        -- 0..100
  geom geography(Polygon,4326),    -- tract boundary if available, else null
  centroid geography(Point,4326) not null
);

create table pois (
  poi_id text primary key,         -- 'osm-<type>-<id>'
  name text,
  category text not null check (category in ('grocery','health','library','education')),
  geom geography(Point,4326) not null
);

create table tract_access (        -- baseline, one row per tract
  geoid text primary key references tracts(geoid),
  score_grocery numeric not null,
  score_health numeric not null,
  score_library numeric not null,
  score_education numeric not null,
  access_score numeric not null,   -- mean, 0..100
  computed_at timestamptz not null default now()
);

create table simulations (
  id uuid primary key default gen_random_uuid(),
  label text,                      -- user label e.g. 'Scenario A', else auto
  kind text not null check (kind in ('stop','route')),
  target_id text not null,         -- stop_id or route_id closed
  created_at timestamptz not null default now(),
  total_residents_affected int not null,
  avg_score_drop numeric not null,
  best_fix jsonb                   -- {lat, lon, recovered_score, note} or null
);

create table simulation_impacts (  -- one row per tract per simulation
  simulation_id uuid not null references simulations(id) on delete cascade,
  geoid text not null references tracts(geoid),
  score_before numeric not null,
  score_after numeric not null,
  score_drop numeric not null,
  residents_affected int not null,
  reason text,                     -- one plain-English sentence, generated from which category fell most
  primary key (simulation_id, geoid)
);
```

Indexes: GIST on every `geom` column; index on `route_stops(route_id)` and `(stop_id)`; index on `simulation_impacts(simulation_id, score_drop desc)`.

Ingest must be re-runnable (`scripts/ingest_gtfs.py`, `scripts/ingest_census.py`, `scripts/ingest_pois.py`, then `scripts/compute_baseline.py`) and idempotent (upserts / truncate-and-reload per dataset, documented in the script header).

## 8. Tech stack (fixed — do not swap without asking)

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui components, in `apps/web/` or repo root — pick repo root for the web app, keep it simple.
- **Map:** MapLibre GL JS for the basemap + **Deck.gl** layers (GeoJsonLayer for tracts, ScatterplotLayer for stops/POIs, PathLayer for route shapes) — same visualization family Ripple used.
- **Backend / simulation:** FastAPI (Python) in `api/`, using SQLAlchemy + GeoAlchemy2 or raw SQL via psycopg — PostGIS does the spatial work, Python orchestrates. The scoring function from §6 lives here, once.
- **Charts:** Recharts only if needed for the Compare view table/sparkline — no chart library for the main map.
- **Package/runtime:** Node 20+, Python 3.12, Docker Compose for Postgres+PostGIS. Provide `.env.example` (DATABASE_URL, CENSUS API base, no secrets — none of the data sources need keys for the MVP).
- **No auth, no payments, no user accounts in the MVP.** Simulations are shared/public by design in v1; saved scenarios live in the DB keyed by the `simulations.id`.

## 9. API surface (FastAPI — implement exactly these)

- `GET /api/meta` → datasets with vintage + row counts (powers the Method panel).
- `GET /api/tracts` → GeoJSON: every tract with baseline `access_score` + the 4 category scores + population + zero_vehicle_pct.
- `GET /api/stops` → GeoJSON points (id, name, routes serving it).
- `GET /api/routes` → list of routes (id, names, stop count) + GeoJSON shapes where GTFS shapes exist.
- `GET /api/pois?category=` → GeoJSON points.
- `POST /api/simulate` body `{ "kind": "stop" | "route", "target_id": "...", "label": "..."? }` → runs §6, persists `simulations` + `simulation_impacts`, returns the simulation including ranked impacts (top 25 by drop) and `best_fix`.
- `GET /api/simulations/:id` → same payload, reloaded (for shareable state / Compare).
- `GET /api/compare?a=<sim_id>&b=<sim_id>` → side-by-side totals for the Compare view.
- `POST /api/parse-scenario` body `{ "text": "..." }` → rule-based MVP parser only: match `close/stop/remove <route short name>` or a stop id / stop name substring against the DB, return `{kind, target_id, matched_name}` or a clear "could not match" error the UI shows. **No LLM call in the MVP** — an LLM parser is a post-MVP stretch and must be behind this same endpoint if ever added.

Frontend state: baseline loads on mount; running a simulation swaps tract colors to scenario scores and fills the Impact Queue from the API response — the frontend never computes scores itself.

## 10. UI / design system (good UI is a requirement, not polish)

- Layout, desktop-first, single page: **full-screen map**, a slim top bar (wordmark "Isthmus", search box for stops/routes/scenario text, Method button), a **right panel ~380px** with three stacked sections: (1) Simulate controls, (2) Impact Queue, (3) Best Fix card. Compare view is a toggle that splits the panel and shows mini summary maps/table. Mobile: panel becomes a bottom sheet; map stays visible.
- Color: dark basemap, near-black UI surfaces (`#0E1113`-family), paper-white text, ONE signal color for loss (a warm red/vermillion), one calm teal/green for healthy access. Tract fill = a 5-step sequential scale from teal (high access) to vermillion (low access / big drop), with a visible legend. **No purple/blue gradients. No generic SaaS blue.**
- Type: a strong grotesque for headings (e.g. "Space Grotesk" or system grotesque), and a highly legible text face for panel copy (e.g. "Atkinson Hyperlegible", the face Vigil chose for arm's-length reading) — load from Google Fonts, no other fonts.
- Motion: tract colors transition (~400ms) when a simulation lands; nothing else animates gratuitously. Map fly-to on stop search.
- Copy rules: every number gets a label a non-technical person understands ("Access Score", "estimated residents affected"). Reasons in the Impact Queue are one sentence, no jargon, no raw GEOIDs shown to users (use tract name/area label; fall back to "Tract <last 4 of GEOID>" only if no name exists).
- Accessibility basics: keyboard-focusable panel controls, color legend also readable by the numbers (never color-only meaning), `prefers-reduced-motion` respected for the color transition.
- Empty/error states are designed, not defaulted: no simulation yet → Impact Queue shows "Close a stop or route to see who is affected"; unmatched scenario text → inline error under the search box; API down → banner with a retry button.

## 11. Build phases (in order — commit after each phase, do not skip ahead)

**Phase 0 — Scaffold.** Repo layout (`apps` not needed: web at root, `api/`, `scripts/`, `docker-compose.yml`, `README.md` stub, `.env.example`, `.gitignore`). `docker compose up` gives a PostGIS DB with the §7 schema applied via a migration/init SQL file. Acceptance: fresh clone → compose up → schema exists (`\dt` shows all tables).

**Phase 1 — Ingest.** The three ingest scripts + `compute_baseline.py` from §5/§6. Acceptance: scripts run end to end on real data; `datasets.row_counts` logs real counts (assert stops > 1000, routes > 20); `tract_access` has one row per tract and every score is 0–100; a spot check by hand: a campus-area tract scores higher on Education than a far-west tract — log the two tracts and scores in the PR/commit message or `NOTES.md`.

**Phase 2 — Read-only map.** Next.js page, MapLibre + Deck.gl: tract choropleth from `/api/tracts`, stop dots, route lines, POI toggle by category, legend, Method panel from `/api/meta`. Acceptance: map renders real Madison data, clicking a tract shows its 4 category scores in a small popover, no scores are hardcoded anywhere in the frontend.

**Phase 3 — Simulation.** `/api/simulate` + `/api/parse-scenario`, Simulate controls, Impact Queue, Best Fix card. Acceptance: closing Route 80 and closing one campus stop both return persisted simulations; **automated test: no tract's score increases in any simulation**; Impact Queue reasons are present for the top 10 impacts; Best Fix returns a location and a positive recovered score or an explicit null with a UI note.

**Phase 4 — Compare + polish.** Save/label scenarios, `/api/compare`, Compare view, empty/error states, README with demo instructions + a screenshot, final design pass against §10. Acceptance: the exact 60-second demo in §4 can be performed start to finish with no console errors and no manual DB touching.

**Phase 5 — Tests + cleanup (do not skip).** Pytest for the scoring function (walk-only case, unreachable case, closure-never-helps case, score formula at t=15/45 boundaries), one API test for `/api/simulate` on a seeded mini-fixture, `npm run build` + lint clean, remove dead code and debug logging.

## 12. Out of scope for the MVP (do not build these)

User accounts / login, payments, a mobile native app, real-time bus positions (GTFS-RT), door-to-door routing/directions, an LLM scenario parser, editing/adding routes or stops by hand, any city other than Madison, historical GTFS comparison, email/sharing integrations. Saved-scenario URLs keyed by simulation id are in scope; social sharing is not.

## 13. Guardrails for Claude

- Work phase by phase (§11). Finish and verify a phase before starting the next. Commit after each phase with a message naming the phase.
- Never fabricate data. If GTFS/Census/Overpass is unreachable, retry once, then stop and report the exact error and URL — do not seed fake stops, tracts, or POIs to "keep going".
- All scores come from the one scoring function (§6) reading the database. If you find yourself typing a score, a resident count, or a tract result into frontend code, stop — that belongs in the API.
- Keep `CLAUDE.md` short: stack, commands, phase pointer, these guardrails. Put detail here in `BRIEF.md`, not in `CLAUDE.md`.
- When a choice is genuinely ambiguous and reversible, pick the simpler option and note it in `NOTES.md`. When it changes the data model, the scoring formula, or the stack (§8), stop and ask the human.
- Run the Phase 5 tests before declaring the project done. "It renders" is not done.

## 14. Definition of done

A fresh clone following only the README can: start PostGIS, run the four scripts, start API + web, open the app, perform the §4 demo (close Route 80 → see the Impact Queue → see a Best Fix → save A, run B, compare), open the Method panel and read the real dataset vintages and counts, and run the test suites green. Plus: README contains one real screenshot of the Madison map with a simulation applied.

---

## Appendix — file layout (target)

```
/
  README.md            -- pitch, demo steps, setup, screenshot
  BRIEF.md             -- this file
  CLAUDE.md            -- short working instructions for Claude Code
  NOTES.md             -- decisions taken, spot-check results, known limits of the proxy model
  docker-compose.yml   -- Postgres 16 + PostGIS
  .env.example
  db/
    schema.sql         -- §7 schema
  scripts/
    ingest_gtfs.py
    ingest_census.py
    ingest_pois.py
    compute_baseline.py
  api/
    main.py            -- FastAPI app, §9 endpoints
    scoring.py         -- §6, the single scoring implementation
    requirements.txt
    tests/
  (web app at repo root: app/, components/, lib/, package.json, tailwind config)
    components: MapView, ImpactQueue, SimulatePanel, BestFixCard, CompareView, MethodPanel, Legend
```
