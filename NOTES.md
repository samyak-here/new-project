# Isthmus — engineering notes & decisions

Decisions a future reader (or Claude session) should not have to re-derive.
Spec source of truth is `BRIEF.md`; this file records where the build made a
choice the brief left open, and every deviation.

## Scoring lives in one pure-Python module

BRIEF §6/§7 allow implementing the walking/riding reachability in SQL/PostGIS
or in application code. Isthmus implements it **once**, in `api/scoring.py`,
as pure Python over lat/lon rows (haversine distances). Postgres + PostGIS
remains the system of record (the §7 schema keeps `geometry`/`geography`
columns and GIST indexes), and the API loads rows from Postgres and runs the
same module. Why: the math is unit-testable without a database
(`api/tests/test_scoring.py`, 8 tests), there is exactly one implementation so
the map, the API and the baseline can never disagree, and county scale is
small (125 tracts, 1,681 stops, ~10³ POIs — a few seconds in memory).

## Deviations from BRIEF.md

1. **Census API key (§5.2).** As of 2026-11-09, `api.census.gov` rejects
   keyless requests: HTTP 302 to `missing_key.html` with header
   `X-DataWebAPI-KeyError: 1` (verified live). `scripts/ingest_census.py`
   therefore uses the official API **only when `CENSUS_API_KEY` is set**, and
   otherwise falls back to **Census Reporter**, which republishes the same
   ACS 5-year tables (B01003, B19013, B25044) without a key. Same source data,
   different mirror. Geometry still comes from the Census Bureau's GENZ
   cartographic-boundary KML (TIGERweb REST as fallback), exactly per brief.

2. **Route shapes in DB mode (§7 vs §9).** The §7 schema has no table for
   GTFS `shapes.txt`, so when the API runs against Postgres, `GET /api/routes`
   returns routes **without line geometry** (`geometry: null`); the frontend
   then simply has no route lines to draw. The JSON snapshot (demo mode)
   includes shapes parsed at ingest time. Fix later by adding a
   `route_shapes` table; the schema was implemented verbatim per the brief.

3. **Best-fix recovery accounting (§6).** §6 says "recovered Access Score
   points (summed over affected tracts)". Implemented literally as the sum,
   over tracts that lost access, of score gained when the candidate stop is
   added. Candidates are evaluated exactly per the brief (closed stops the
   fix-route already passes near + the 5 worst tracts' nearest surviving
   stops). The label everywhere is "best fix found", never "optimal".

4. **Snapshot demo mode.** As specified in the build task: with no
   `DATABASE_URL`, the API serves `data/snapshot.json` **only** when
   `scripts/export_snapshot.py` produced it from real ingest dry-runs, and
   answers 503 with setup instructions otherwise. It never invents data.
   In demo mode simulations are computed live by the same scoring module and
   held in memory (they do not persist across API restarts).

5. **Atkinson Hyperlegible (§10)** is loaded from Google Fonts, with Inter as
   fallback, per the brief's "if loadable" allowance. Mono is JetBrains Mono
   (Google substitute for Fabrikatmono, as the brief allows).

## Verified data behaviour (2026-11-09, this machine)

- GTFS dry-run: 29 routes, 1,681 stops, 2,805 route–stop pairs, 29 shapes —
  matches the brief's stated snapshot exactly. Feed vintage `S072_202608240858`.
- Census dry-run: ACS 2024 5-year (via Census Reporter), 125 Dane County
  tracts, 0 missing GENZ2024 KML geometry.
- Overpass: the public endpoint needs a descriptive `User-Agent` (a generic
  one gets HTTP 406) and is slow from some networks; the script retries once
  per endpoint, then tries the kumi.systems mirror, and logs exact errors.

## Things deliberately not built (BRIEF §12)

No auth, no accounts, no GTFS-Realtime, no other cities, no mobile app, no
emitted "city report card", no LLM anywhere (the scenario parser in
`api/parsing.py` is hand-written rules).

## Frontend gotcha worth remembering

`maplibre-gl.css` is *unlayered* CSS, and Tailwind v4 emits utilities into
`@layer utilities`. Unlayered rules beat layered ones regardless of order, so
MapLibre's `.maplibregl-map { position: relative }` silently overrode the
container's Tailwind `absolute inset-0`, collapsing the map container to
height 0 (found by probing the live DOM — the map simply never painted).
`components/MapView.tsx` therefore positions its container with an inline
style, which no stylesheet can override. If the map ever renders blank with a
~300px-tall canvas, check this first.

## Docker note

`docker-compose.yml` mounts `db/schema.sql` into the PostGIS image's
initdb directory, so the schema is created on first `docker compose up`.
This VM has no Docker, so the compose stack itself was not run here — see
RESULTS.md for what was verified instead.
