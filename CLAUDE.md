# CLAUDE.md — Isthmus

Read `BRIEF.md` first. It is the single source of truth for this project: idea, data sources, Access Score formula (§6), database schema (§7), API (§9), UI rules (§10), and build phases (§11).

## Project in one line

Isthmus: a Madison, WI transit what-if simulator. Close a bus stop or route on a map, see which neighborhoods lose access to groceries / health / libraries / education, ranked, with a best-fix suggestion.

## Stack (fixed, see BRIEF §8)

- Next.js (App Router) + TypeScript + Tailwind + shadcn/ui — web app at repo root
- MapLibre GL + Deck.gl for the map (no Mapbox token, no paid tiles)
- FastAPI (Python 3.12) in `api/` — all scoring lives here, once, in `api/scoring.py`
- Postgres 16 + PostGIS via `docker-compose.yml` — schema in `db/schema.sql` (BRIEF §7)

## Design — Altius (read before any UI work)

The visual system is **Altius** ("molten embers on obsidian", from Refero Styles). Its full files are in `design/altius/`: `DESIGN.md` (the reference — read it first), `tokens.json`, `variables.css`, `theme.css` (Tailwind v4 `@theme`). Use those tokens, do not invent a palette.

Isthmus adaptations of Altius (these override the raw Altius files where they conflict):
- The app is **fully dark, always**. Do NOT use Altius's light Vapor Peach / Linen sections — no light panels anywhere.
- **Flare Orange `#fa5838` is rationed**: ember glow only on tracts that lost access, the Best Fix card (the one filled, glowing surface), and thermal-bar accents in the Impact Queue. Everything else is obsidian/cocoa surfaces, hairline borders, linen text.
- The calm **teal for healthy access is a data color only** (tract fills / access readouts), never a UI accent, never in a gradient with orange. The only gradient allowed is Altius's single-hue orange peak-to-zero fade, on data bars only.
- Panel chrome borrows terminal discipline: mono (Fabrikatmono per Altius, JetBrains Mono/IBM Plex Mono substitutes are fine) for all numbers, stop/route/tract IDs, and deltas. Tighten Altius's comfortable density in the ~380px panel: 16px card padding, 12px element gap.
- BRIEF §10 still governs layout, copy, and accessibility; Altius governs color, type, glow, and shape.

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
