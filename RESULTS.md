# Isthmus — build results (Phases 0–5)

Built 2026-11-09 in this workspace. After independent verification
(parent re-ran pytest: 12 passed), this snapshot was pushed to GitHub
branch `implement/isthmus` on samyak-here/new-project, commit d52e430.
BRIEF.md, CLAUDE.md and design/ were not edited. README.md was updated with real setup instructions; NOTES.md records
decisions and deviations.

## File inventory (excluding node_modules/, .next/, .venv/, caches)

```
.env.example  .gitignore  docker-compose.yml  package.json  package-lock.json
tsconfig.json  next.config.mjs  postcss.config.mjs  next-env.d.ts
README.md  BRIEF.md  CLAUDE.md  NOTES.md  RESULTS.md
db/schema.sql                       BRIEF §7 verbatim + pgcrypto + named GIST/FK indexes
design/altius/{DESIGN.md,tokens.json,variables.css,theme.css}   (pre-existing, untouched)
scripts/common.py                   fetch-with-one-retry, exact-error logging, dotenv, DB connect
scripts/ingest_gtfs.py              GTFS -> Postgres, or --dry-run [--out data/gtfs.json]
scripts/ingest_census.py            ACS -> Postgres, or --dry-run [--out data/census.json]
scripts/ingest_pois.py              Overpass -> Postgres, or --dry-run [--out data/pois.json]
scripts/compute_baseline.py         baseline Access Scores -> tract_access (DB) or --use-json-dir
scripts/export_snapshot.py          dry-runs -> data/snapshot.json (fails loudly on missing input)
api/scoring.py                      THE one implementation of BRIEF §6 (pure Python, haversine)
api/data.py                         DbSource (psycopg) | SnapshotSource (demo) | honest 503
api/parsing.py                      rule-based scenario parser (no LLM)
api/main.py                         FastAPI app, BRIEF §9 endpoints exactly
api/requirements.txt
api/tests/test_scoring.py           8 tests
api/tests/test_api.py               4 tests (tiny in-memory fixture)
app/layout.tsx  app/globals.css  app/page.tsx
lib/api.ts                          typed API client + score color scale
components/MapView.tsx              MapLibre + Deck.gl overlay (+ MapLibre-only fallback path)
components/SimulatePanel.tsx  components/ImpactQueue.tsx  components/BestFixCard.tsx
components/CompareView.tsx    components/MethodPanel.tsx  components/Legend.tsx
data/gtfs.json  data/census.json  data/pois.json  data/snapshot.json   (real ingested data)
```

## Verified — with actual command output

### Tests (Phase 5)
```
$ .venv/bin/python -m pytest api/tests -q
12 passed, 1 warning in 0.50s
```
8 scoring tests: walk-only access, bus access, unreachable category = 0,
t = 15:00 → 100 and t = 45:00 → 0 boundaries, closing a route never raises
any tract's score, closing a stop never raises any score (only its users are
affected), best-fix returns a positive recovery or None, residents-affected
formula. 4 API tests on a tiny in-memory fixture: meta/tracts shape,
POST /api/simulate end-to-end + GET /api/simulations/{id}, 404/400 handling,
parse-scenario match + miss, compare shape.

### Frontend build (Phase 5)
```
$ npm run build        (Next.js 15.5.29, final production config)
✓ Compiled successfully
✓ Generating static pages (4/4)
Route (app)  /  → 216 kB, First Load JS 319 kB
EXIT=0
```
`npm install` added 120 packages including @deck.gl/* 9.x — **Deck.gl is
installed and used; the fallback was not needed** (it remains in code as a
runtime safety net).

### Ingest dry-runs with REAL downloaded data (Phase 1)
```
GTFS  (https://transitdata.cityofmadison.com/GTFS/mmt_gtfs.zip, 7.0 MB, redirect followed)
  vintage S072_202608240858
  routes=29  stops=1681  route_stops=2805  shapes=29     <- matches BRIEF exactly
CENSUS (ACS 2024 5-year via Census Reporter; GENZ2024 cartographic KML geometry)
  tracts=125  tracts_missing_geometry=0                  <- all of Dane County (55/025)
POIS  (Overpass API, overpass-api.de served all four categories)
  grocery=171  health=108  library=28  education=114  total=421
BASELINE (scripts/export_snapshot.py -> data/snapshot.json, 1.25 MB)
  tracts=125  mean_access=60.2  min=0  max=100
  spot check: campus-area tract 55025001102 education=100.0, access=100
              far-west tract 55025000406 education=93.3, access=90
```
Spot-check note: the brief's expectation holds for the campus tract (Education
100). The far-west tract's Education is also high (93.3) because the brief's
education category includes all schools (`amenity=school|university|college`)
and suburban tracts have schools nearby — the category definition was applied
exactly as written. 46 of 125 county tracts score 0: they are fringe/rural
tracts whose *centroid* (the brief's tract representation) falls more than
800 m from the nearest stop and any POI — e.g. tract 55025001405's centroid is
1.02 km from its nearest stop. That is §6 applied literally, and the Method
panel carries the brief's "simplified proxy" wording.

### Live API smoke test (demo mode, real snapshot)
All §9 endpoints exercised against uvicorn + data/snapshot.json:
- GET /api/meta → 3 datasets with vintages + row counts; demo_mode=true
- GET /api/tracts → 125 features with baseline scores (e.g. Tract 1 = 100)
- GET /api/routes → 29 routes (Route D has the most stops: 271)
- GET /api/pois?category=library → 28 features; ?category=zzz → HTTP 400
- POST /api/parse-scenario {"text":"Close Route D"} → matched route D
- POST /api/simulate closing Route D → 1,530 est. residents affected, avg
  drop 0.61; worst tract: Tract 25, 100 → 25 (−75; health access 100 → 0,
  one-sentence reason present); Best Fix found: temporary stop at
  43.13159, −89.33950 served by Route L, +75 points recovered
- GET /api/simulations/{id} round-trips the simulation; GET /api/compare
  returns both summaries with worst tract + best fix
- With data/snapshot.json removed and no DATABASE_URL: GET /api/tracts →
  **HTTP 503** {"detail": "No data available: DATABASE_URL is not set and
  data/snapshot.json does not exist. Run the ingest scripts (see README) —
  the API never serves invented data."}

### Live frontend smoke test (production build + headless Chromium/Playwright)
- Page loads, all panels render (top bar + search, layer toggles, legend,
  Simulate, Impact Queue empty state with the brief's exact wording,
  Compare), route dropdown populated from the real API.
- Map renders: probed the live DOM — `.maplibregl-map` 1440×900, WebGL2
  context OK — and screenshotted the Deck.gl choropleth over real data
  (teal Madison tracts, lakes cut out, stop dots, POI dots). Screenshot was
  taken against a local blank test style because this VM's browser cannot
  fetch CARTO through its credentialed egress proxy (see below); the shipped
  code uses the CARTO dark style URL, verified reachable via curl (HTTP 200).
- A real bug was found and fixed by this testing: MapLibre's unlayered CSS
  overrode Tailwind's layered `absolute inset-0`, collapsing the map
  container to height 0. Fixed with inline positioning (see NOTES.md).

## NOT verified here — and why

- **Postgres/PostGIS end-to-end (docker compose up, DB ingest, DB-mode API,
  simulation persistence): NOT run — this VM has no Docker.** The schema is
  BRIEF §7 verbatim, all DB code paths use the same tested scoring module,
  and queries are plain psycopg SQL, but the first real DB run happens on the
  user's machine (`docker compose up -d db` + the README Option A commands).
- **CARTO basemap tiles inside a browser on this VM:** the VM's egress proxy
  requires credentials Chromium cannot supply, so basemap tiles could not be
  fetched by the test browser. The style URL itself returns HTTP 200 via
  curl, and the map + all Deck layers were verified against a local style.
  On a normal network this is a non-issue.
- **Ember-flip screenshot after a simulated closure:** the flip is the same
  Deck layer re-rendered with scenario scores (API response verified, layer
  transition configured at 400 ms); a pixel-level before/after screenshot was
  not captured in this environment.

## Deviations from BRIEF.md (details in NOTES.md)

1. **Census without an API key:** api.census.gov now requires a key
   (verified: HTTP 302 → missing_key.html, `X-DataWebAPI-KeyError: 1`).
   ingest_census.py uses the official API when `CENSUS_API_KEY` is set, else
   Census Reporter (same ACS 5-year tables, keyless). Data returned: ACS 2024
   5-year, 125 tracts.
2. **Route shapes in DB mode:** the §7 schema has no shapes table, so
   DB-mode /api/routes returns geometry=null; snapshot mode includes shapes
   from GTFS shapes.txt. Schema kept verbatim per brief.
3. **Overpass query fixes during bring-up:** the endpoint rejects generic
   User-Agents (HTTP 406) and `out center tags;`/union-parenthesis forms are
   parse errors; the script uses `out center;` with a descriptive UA. Final
   run: all four categories served by overpass-api.de, no mirror needed.
4. **API impacts payload:** returns the top 25 tracts with score_drop > 0
   (zero-change tracts are noise in the queue); the DB persistence path still
   stores every impacted tract.
