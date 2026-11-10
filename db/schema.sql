-- Isthmus schema — BRIEF.md §7, verbatim structure.
-- Applied automatically by docker-compose (mounted into /docker-entrypoint-initdb.d)
-- and can also be applied manually: psql "$DATABASE_URL" -f db/schema.sql
create extension if not exists postgis;
create extension if not exists pgcrypto;  -- for gen_random_uuid() on simulations.id

create table if not exists datasets (
  id serial primary key,
  source text not null,            -- 'madison_gtfs' | 'acs' | 'osm'
  vintage text,                    -- e.g. GTFS feed date / ACS year / OSM extract date
  ingested_at timestamptz not null default now(),
  row_counts jsonb not null        -- actual counts logged at ingest, e.g. {"stops": 1681}
);

create table if not exists routes (
  route_id text primary key,       -- GTFS route_id
  short_name text, long_name text,
  color text
);

create table if not exists stops (
  stop_id text primary key,        -- GTFS stop_id
  name text not null,
  geom geography(Point,4326) not null
);

create table if not exists route_stops (         -- from trips + stop_times, deduplicated
  route_id text not null references routes(route_id),
  stop_id  text not null references stops(stop_id),
  primary key (route_id, stop_id)
);

create table if not exists tracts (
  geoid text primary key,          -- census tract GEOID
  name text,                       -- tract label for display
  population int not null default 0,
  median_income int,
  zero_vehicle_pct numeric,        -- 0..100
  geom geography(Polygon,4326),    -- tract boundary if available, else null
  centroid geography(Point,4326) not null
);

create table if not exists pois (
  poi_id text primary key,         -- 'osm-<type>-<id>'
  name text,
  category text not null check (category in ('grocery','health','library','education')),
  geom geography(Point,4326) not null
);

create table if not exists tract_access (        -- baseline, one row per tract
  geoid text primary key references tracts(geoid),
  score_grocery numeric not null,
  score_health numeric not null,
  score_library numeric not null,
  score_education numeric not null,
  access_score numeric not null,   -- mean, 0..100
  computed_at timestamptz not null default now()
);

create table if not exists simulations (
  id uuid primary key default gen_random_uuid(),
  label text,                      -- user label e.g. 'Scenario A', else auto
  kind text not null check (kind in ('stop','route')),
  target_id text not null,         -- stop_id or route_id closed
  created_at timestamptz not null default now(),
  total_residents_affected int not null,
  avg_score_drop numeric not null,
  best_fix jsonb                   -- {lat, lon, recovered_score, note} or null
);

create table if not exists simulation_impacts (  -- one row per tract per simulation
  simulation_id uuid not null references simulations(id) on delete cascade,
  geoid text not null references tracts(geoid),
  score_before numeric not null,
  score_after numeric not null,
  score_drop numeric not null,
  residents_affected int not null,
  reason text,                     -- one plain-English sentence, generated from which category fell most
  primary key (simulation_id, geoid)
);

-- Indexes (BRIEF §7): GIST on every geom column + the named lookup indexes.
create index if not exists stops_geom_gix        on stops        using gist (geom);
create index if not exists tracts_geom_gix       on tracts       using gist (geom);
create index if not exists tracts_centroid_gix   on tracts       using gist (centroid);
create index if not exists pois_geom_gix         on pois         using gist (geom);
create index if not exists route_stops_route_ix  on route_stops  (route_id);
create index if not exists route_stops_stop_ix   on route_stops  (stop_id);
create index if not exists simulation_impacts_rank_ix
  on simulation_impacts (simulation_id, score_drop desc);
