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

**Start with [`BRIEF.md`](BRIEF.md)** — it is the full, Claude-Code-ready project brief: data sources, exact scoring definition, database schema, API surface, UI/design system, build phases with acceptance criteria, and what is explicitly out of scope. [`CLAUDE.md`](CLAUDE.md) has the short working rules.

## Status

Brief only — not built yet. The brief is written to be handed to Claude Code and built phase by phase (Phases 0–5 in `BRIEF.md` §11).
